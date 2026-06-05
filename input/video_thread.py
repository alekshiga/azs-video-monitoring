import time

import torch
from PyQt6.QtCore import QThread, pyqtSignal

from core.alert_filter import AlertFilter
from core.anpr import PlateRecognizer
from core.database import Database
from core.detection import MotionDetector
from core.scenario_analyzer import ScenarioAnalyzer
from core.stats_tracker import StatsTracker, VEHICLE_CLASSES
from core.zone_manager import ZoneManager
from input.source_manager import SourceManager
from output.incident_storage import save_snapshot


class VideoThread(QThread):
    all_frames_ready = pyqtSignal(list)
    log_signal = pyqtSignal(str)
    alert_signal = pyqtSignal(int, object, int, str, float)
    camera_status_changed = pyqtSignal(int, bool)  # source_id, is_connected
    stats_updated = pyqtSignal(int)                 # source_id
    plate_recognized = pyqtSignal(int, str, float)  # source_id, plate, confidence

    def __init__(self, source_manager: SourceManager):
        super().__init__()
        self.running = False
        self.source_manager = source_manager

        self.frame_counters = {}
        self.detectors = {}
        self.zone_managers = {}
        self.alert_filters = {}
        self.scenario_analyzers = {}

        self.model_name = "yolov8m.pt"
        self.confidence = 0.45
        self.watched_classes = {0, 2, 5, 7}
        self.draw_rectangles = True
        self.min_presence_time = 2.0
        self.alert_cooldown = 30.0
        self.min_overlap_ratio = 0.1

        # Настройки сценариев
        self.person_without_car_delay = 60.0
        self.max_person_time = 600.0
        self.track_zone_time = {}
        self.rule_last_alert = {}
        self.cond_rule_since = {}

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"VideoThread: {self.device.upper()}")
        self._source_connected_state = {}
        self.db = Database()
        self.stats_tracker = StatsTracker(db=self.db)

        # Automatic Number Plate Recognition
        self.anpr_enabled = True
        self.anpr_debug = False   # сохранять обработанные кропы (только для отладки)
        self.anpr = PlateRecognizer(gpu=(self.device == 'cuda'))
        self.repeat_visit_window = 3600.0   # окно (сек) для подсчёта повторных визитов
        # Дедупликация по самому номеру (track_id нестабилен): не регистрируем
        # один и тот же номер чаще, чем раз в plate_log_cooldown секунд.
        self._plate_last_logged = {}        # plate -> ts последней записи в БД
        self.plate_log_cooldown = 60.0
        self._plate_alert_last = {}          # plate -> ts последней тревоги по номеру
        self.plate_alert_cooldown = 300.0    # не чаще раза в 5 минут на номер

    def init_source(self, source_id):
        if source_id in self.zone_managers:
            return

        if source_id not in self.detectors:
            self.detectors[source_id] = MotionDetector(
                model_name=self.model_name,
                confidence=self.confidence,
                device=self.device,
                watched_classes=self.watched_classes
            )

        zm = ZoneManager()
        zones_file = self.source_manager.get_zones_file(source_id)
        if zones_file and zm.load_from_file(zones_file):
            self.log_signal.emit(
                f"Камера {source_id}: автозагружено зон {len(zm.zones)}, "
                f"правил {sum(len(r) for r in zm.zone_rules.values())}"
            )
        self.zone_managers[source_id] = zm

        self.alert_filters[source_id] = AlertFilter(
            min_presence_time=self.min_presence_time,
            alert_cooldown=self.alert_cooldown,
            min_ratio=self.min_overlap_ratio
        )

        self.scenario_analyzers[source_id] = ScenarioAnalyzer(
            person_without_car_delay=self.person_without_car_delay,
            max_person_time=self.max_person_time
        )

        self.frame_counters[source_id] = 0

    def update_zones(self, zones, source_id, zone_names=None, zone_rules=None, zone_types=None):
        if source_id in self.zone_managers:
            zm = self.zone_managers[source_id]
            zm.set_zones(
                zones,
                zone_names,
                zone_rules if zone_rules is not None else zm.zone_rules,
                zone_types if zone_types is not None else zm.zone_types,
            )
            self.track_zone_time.clear()
            self.rule_last_alert.clear()

    def remove_source(self, source_id):
        self.detectors.pop(source_id, None)
        self.zone_managers.pop(source_id, None)
        self.alert_filters.pop(source_id, None)
        self.scenario_analyzers.pop(source_id, None)
        self.frame_counters.pop(source_id, None)

    def _process_conditional_rules(self, source_id, objects, zone_manager,
                                   zone_rules, current_time, pending_alerts,
                                   zone_name_of):
        """
        Для каждого правила ведется таймер непрерывного выполнения условия:
            Условие: автомобиль без человека
            если человек пропал, начинаем таймер, если его нет дольше заданного времени,
            то вызываем тревогу, если он появился, обнуляем таймер отсутствия
        """
        active_cond_keys = set()
        for zone_index, rules in zone_rules.items():
            if not rules:
                continue
            # классы, присутствующие в этой зоне на текущем кадре
            present_classes = set()
            for o in objects:
                if o.get('zone_index') != zone_index or not o.get('in_zone'):
                    continue
                cn = o.get('class_name')
                if cn:
                    present_classes.add(cn)
                if cn in VEHICLE_CLASSES:
                    present_classes.add('vehicle')

            for ri, rule in enumerate(rules):
                if not rule.enabled or not getattr(rule, 'is_conditional', False):
                    continue
                ckey = (source_id, zone_index, ri)
                met = rule.condition_met(present_classes)

                if not met:
                    # условие нарушилось - запускаем таймер
                    self.cond_rule_since.pop(ckey, None)
                    continue

                active_cond_keys.add(ckey)
                # запускаем таймер при первом выполнении
                started = self.cond_rule_since.setdefault(ckey, current_time)
                held = current_time - started
                if held < rule.duration:
                    continue  # условие выполнено, ждем превышение времени

                # нарушение активно - заливка зоны красным и отправка тревоги
                for o in objects:
                    if o.get('zone_index') == zone_index and o.get('in_zone'):
                        o['is_violation'] = True

                alert_key = (zone_index, 'cond', ri)
                if current_time - self.rule_last_alert.get(alert_key, 0) < rule.cooldown:
                    continue
                self.rule_last_alert[alert_key] = current_time
                message = rule.describe()
                pending_alerts.append((zone_index, source_id, message, held))
                self.db.insert_event(
                    source_id, zone_index, zone_name_of(zone_index), "alert",
                    class_name=None, track_id=None,
                    ts=current_time, message=message,
                )

        for k in list(self.cond_rule_since):
            if k[0] == source_id and k not in active_cond_keys:
                self.cond_rule_since.pop(k, None)

    def _process_anpr(self, source_id, frame, objects, current_time):
        """
        Распознаёт номера у транспортных средств в кадре. При первом устойчивом
        распознавании для трека: пишет номер в БД, проверяет чёрный/белый список
        и повторные визиты, при необходимости формирует тревогу.
        """
        active_vehicle_tracks = set()
        for obj in objects:
            if obj.get('class_name') not in VEHICLE_CLASSES:
                continue
            track_id = obj.get('track_id')
            bbox = obj.get('bbox')
            if track_id is None or bbox is None:
                continue
            active_vehicle_tracks.add(track_id)

            best = self.anpr.process_vehicle(frame, bbox, track_id, current_time,
                                             debug=self.anpr_debug)
            if not best:
                continue
            plate = best['plate']
            conf = best['conf']
            obj['plate'] = plate  # для отрисовки на кадре

            last_log = self._plate_last_logged.get(plate, 0)
            if current_time - last_log < self.plate_log_cooldown:
                continue
            self._plate_last_logged[plate] = current_time

            # повторные визиты считаем ДО записи текущего
            prior_visits = self.db.plate_visit_count(
                plate, since=current_time - self.repeat_visit_window
            )
            snap = save_snapshot(frame, source_id, -1)
            self.db.insert_plate(source_id, track_id, plate, conf,
                                 snapshot=snap, ts=current_time)
            self.plate_recognized.emit(source_id, plate, conf)
            self.log_signal.emit(f"Распознан номер: {plate} ({conf:.0%})")

            alert_last = self._plate_alert_last.get(plate, 0)
            if current_time - alert_last < self.plate_alert_cooldown:
                continue
            watch = self.db.get_watch_status(plate)
            src = self.source_manager.get_source(source_id)
            cam_name = src.name if src else f"Камера {source_id}"
            msg = None
            if watch == "black":
                msg = f"Номер {plate} в чёрном списке"
            elif prior_visits >= 2:
                msg = f"Повторный визит {plate} ({prior_visits + 1}-й раз за час)"
            if msg:
                self._plate_alert_last[plate] = current_time
                self.db.insert_alert(source_id, cam_name, -1, "ANPR",
                                     class_name=plate, message=msg, snapshot=snap,
                                     ts=current_time)
                self.alert_signal.emit(-1, frame.copy(), source_id, msg, 0.0)
                self.log_signal.emit(f"ТРЕВОГА: {msg}")

        self.anpr.cleanup(active_vehicle_tracks)

    def run(self):
        self.running = True
        self.log_signal.emit("Поток видео запущен")
        self.source_manager.connect_all()

        while self.running:
            start_time = time.time()
            all_frames = []

            for source_id, source in list(self.source_manager.sources.items()):
                self.init_source(source_id)

                # Отслеживаем смену статуса подключения и эмитим сигнал
                prev_connected = self._source_connected_state.get(source_id)
                curr_connected = source.is_connected
                if prev_connected != curr_connected:
                    self._source_connected_state[source_id] = curr_connected
                    self.camera_status_changed.emit(source_id, curr_connected)
                    if curr_connected:
                        self.log_signal.emit(f"Камера {source.name}: восстановлено соединение")
                    else:
                        attempts = getattr(source, 'reconnect_attempts', 0)
                        self.log_signal.emit(f"Камера {source.name}: соединение потеряно, переподключение каждые 10 сек")

                frame = source.get_last_frame()

                if frame is None:
                    all_frames.append({'id': source_id, 'frame': None, 'objects': [], 'active_zones': set()})
                    continue

                self.frame_counters[source_id] += 1

                objects, annotated_frame = self.detectors[source_id].detect(
                    frame, self.zone_managers[source_id].zones
                )

                zone_manager = self.zone_managers[source_id]
                for obj in objects:
                    bbox = obj.get('bbox')
                    if bbox:
                        zones = zone_manager.get_all_intersections(bbox, self.min_overlap_ratio)
                        obj['in_zone'] = len(zones) > 0
                        obj['zone_index'] = zones[0] if zones else None
                    else:
                        obj['in_zone'] = False
                        obj['zone_index'] = None

                current_time = time.time()
                zone_rules = zone_manager.zone_rules

                if self.anpr_enabled:
                    self._process_anpr(source_id, frame, objects, current_time)

                present_keys = {
                    (obj['track_id'], obj['zone_index'])
                    for obj in objects
                    if obj.get('track_id') is not None
                    and obj.get('zone_index') is not None
                    and obj.get('in_zone')
                    and zone_manager.is_counting_zone(obj['zone_index'])
                }

                def zone_name_of(zi):
                    return (zone_manager.zone_names[zi]
                            if zi is not None and zi < len(zone_manager.zone_names)
                            else f"Зона {zi}")

                pending_alerts = []

                for obj in objects:
                    obj['is_violation'] = False  # по умолчанию нарушения нет
                    track_id = obj.get('track_id')
                    zone_index = obj.get('zone_index')

                    if track_id is None or zone_index is None:
                        continue

                    rules = zone_rules.get(zone_index, [])
                    is_counting = zone_manager.is_counting_zone(zone_index)

                    key = (track_id, zone_index)

                    if obj.get('in_zone'):
                        if key not in self.track_zone_time:
                            self.track_zone_time[key] = current_time
                            # Конверсия и визиты считаются ТОЛЬКО в зоне подсчёта.
                            # Зоны контроля дают только тревоги, в статистику потока
                            # они не идут (иначе случайный транспорт портит конверсию).
                            if is_counting:
                                self.stats_tracker.record_entry(
                                    source_id, track_id, zone_index,
                                    obj.get('class_name', 'unknown'), current_time,
                                    zone_name=zone_name_of(zone_index),
                                )
                                self.stats_updated.emit(source_id)

                        time_in_zone = current_time - self.track_zone_time[key]

                        # Простые правила (по классу объекта) - таймер по объекту
                        for rule in rules:
                            if not rule.enabled or getattr(rule, 'is_conditional', False):
                                continue
                            class_name = obj.get('class_name')
                            if rule.class_name != "any" and class_name != rule.class_name:
                                continue
                            if time_in_zone < rule.min_time:
                                continue

                            obj['is_violation'] = True

                            alert_key = (zone_index, rule.class_name)
                            if current_time - self.rule_last_alert.get(alert_key, 0) < rule.cooldown:
                                continue
                            self.rule_last_alert[alert_key] = current_time
                            pending_alerts.append((zone_index, source_id, class_name, time_in_zone))
                            self.db.insert_event(
                                source_id, zone_index, zone_name_of(zone_index), "alert",
                                class_name=class_name, track_id=track_id,
                                ts=current_time, message=f"Объект '{class_name}' в зоне",
                            )
                    else:
                        if key in self.track_zone_time:
                            self.track_zone_time.pop(key)

                self._process_conditional_rules(
                    source_id, objects, zone_manager, zone_rules,
                    current_time, pending_alerts, zone_name_of
                )

                # закрытые треки по истечению grace-period
                closed = self.stats_tracker.update_presence(
                    source_id, present_keys, zone_manager.zone_names, current_time
                )
                if closed:
                    self.stats_updated.emit(source_id)

                # Отрисовка по результатам анализа
                if self.draw_rectangles:
                    self.detectors[source_id].draw_rectangles = True
                    self.detectors[source_id].annotate(
                        annotated_frame, objects, zone_manager.zone_names
                    )
                else:
                    self.detectors[source_id].draw_rectangles = False

                for zone_index, src_id, message, t_in_zone in pending_alerts:
                    self.alert_signal.emit(zone_index, annotated_frame.copy(), src_id, message, t_in_zone)

                active_zones = {obj['zone_index'] for obj in objects
                                if obj.get('is_violation') and obj.get('zone_index') is not None}

                all_frames.append({
                    'id': source_id,
                    'frame': annotated_frame,
                    'objects': objects,
                    'active_zones': active_zones
                })

            self.all_frames_ready.emit(all_frames)

            frame_time = time.time() - start_time
            if frame_time < 1.0 / 30.0:
                time.sleep(1.0 / 30.0 - frame_time)

    def stop(self):
        self.running = False
        if self.source_manager:
            self.source_manager.stop_all()
        self.wait()
        if self.db:
            self.db.close()

    def get_zone_manager(self, source_id):
        return self.zone_managers.get(source_id)