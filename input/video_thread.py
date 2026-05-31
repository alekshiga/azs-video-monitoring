import time

import torch
from PyQt6.QtCore import QThread, pyqtSignal

from core.alert_filter import AlertFilter
from core.database import Database
from core.detection import MotionDetector
from core.scenario_analyzer import ScenarioAnalyzer
from core.stats_tracker import StatsTracker
from core.zone_manager import ZoneManager
from input.source_manager import SourceManager


class VideoThread(QThread):
    all_frames_ready = pyqtSignal(list)
    log_signal = pyqtSignal(str)
    alert_signal = pyqtSignal(int, object, int, str, float)
    camera_status_changed = pyqtSignal(int, bool)  # source_id, is_connected
    stats_updated = pyqtSignal(int)                 # source_id

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

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"VideoThread: {self.device.upper()}")
        self._source_connected_state = {}  # source_id -> bool, для отслеживания изменений статуса
        self.db = Database()
        self.stats_tracker = StatsTracker(db=self.db)

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

        self.zone_managers[source_id] = ZoneManager()
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

                active_track_ids = {obj['track_id'] for obj in objects if obj.get('track_id') is not None}
                self.stats_tracker.cleanup_lost_tracks(
                    source_id, active_track_ids, zone_manager.zone_names, current_time
                )

                for obj in objects:
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
                            # Фиксируем вход для статистики (зоны подсчета активны всегда,
                            # зоны контроля активны только если есть правила)
                            if is_counting or rules:
                                entry_zone_name = (
                                    zone_manager.zone_names[zone_index]
                                    if zone_index < len(zone_manager.zone_names)
                                    else f"Зона {zone_index}"
                                )
                                self.stats_tracker.record_entry(
                                    source_id, track_id, zone_index,
                                    obj.get('class_name', 'unknown'), current_time,
                                    zone_name=entry_zone_name,
                                )

                        time_in_zone = current_time - self.track_zone_time[key]

                        for rule in rules:
                            if not rule.enabled:
                                continue

                            if hasattr(rule, 'condition'):
                                has_car = any(
                                    o.get('class_name') == 'car' and o.get('zone_index') == zone_index for o in objects)
                                has_person = any(
                                    o.get('class_name') == 'person' and o.get('zone_index') == zone_index for o in
                                    objects)

                                if rule.check(has_car, has_person, time_in_zone):
                                    alert_key = (zone_index, rule.condition)
                                    last_alert = self.rule_last_alert.get(alert_key, 0)
                                    if current_time - last_alert < rule.cooldown:
                                        continue

                                    self.rule_last_alert[alert_key] = current_time
                                    zone_name = zone_manager.zone_names[zone_index] if zone_index < len(
                                        zone_manager.zone_names) else f"Zone_{zone_index}"

                                    messages = {
                                        "has_person_no_car": "Человек без машины",
                                        "has_car_no_person": "Машина без человека",
                                        "has_both": "Машина и человек в зоне",
                                        "has_none": "Зона пуста"
                                    }
                                    message = messages.get(rule.condition, "Условие выполнено")

                                    self.alert_signal.emit(zone_index, annotated_frame.copy(), source_id, message,
                                                           time_in_zone)
                                    self.db.insert_event(
                                        source_id, zone_index, zone_name, "alert",
                                        class_name=obj.get('class_name'), track_id=track_id,
                                        ts=current_time, message=message,
                                    )
                            else:
                                class_name = obj.get('class_name')
                                if rule.class_name != "any" and class_name != rule.class_name:
                                    continue
                                if time_in_zone < rule.min_time:
                                    continue

                                alert_key = (zone_index, rule.class_name)
                                last_alert = self.rule_last_alert.get(alert_key, 0)
                                if current_time - last_alert < rule.cooldown:
                                    continue

                                self.rule_last_alert[alert_key] = current_time
                                zone_name = zone_manager.zone_names[zone_index] if zone_index < len(
                                    zone_manager.zone_names) else f"Zone_{zone_index}"
                                self.alert_signal.emit(zone_index, annotated_frame.copy(), source_id, class_name,
                                                       time_in_zone)
                                self.db.insert_event(
                                    source_id, zone_index, zone_name, "alert",
                                    class_name=class_name, track_id=track_id,
                                    ts=current_time, message=f"Объект '{class_name}' в зоне",
                                )
                    else:
                        if key in self.track_zone_time:
                            self.track_zone_time.pop(key)
                            if is_counting or rules:
                                zone_name = (
                                    zone_manager.zone_names[zone_index]
                                    if zone_index < len(zone_manager.zone_names)
                                    else f"Зона {zone_index}"
                                )
                                self.stats_tracker.record_exit(
                                    source_id, track_id, zone_index, zone_name, current_time
                                )
                                self.stats_updated.emit(source_id)

                    if not rules:
                        continue

                active_zones = {obj['zone_index'] for obj in objects if
                                obj.get('in_zone') and obj.get('zone_index') is not None}

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