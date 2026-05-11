import time

import cv2
import torch
from PyQt6.QtCore import QThread, pyqtSignal

from core.alert_filter import AlertFilter
from core.detection import MotionDetector
from core.zone_manager import ZoneManager
from input.source_manager import SourceManager


class VideoThread(QThread):
    """
    Поток видео для обработки
    """
    # Сигналы
    frame_ready = pyqtSignal(object, object, object, int)  # frame, active_zones, objects, source_id
    log_signal = pyqtSignal(str)
    source_status_signal = pyqtSignal(int, bool)  # source_id, connected
    alert_signal = pyqtSignal(int, object, int)

    def __init__(self, source_manage: SourceManager):
        """
        Инициализация потока обработки
        :param source_manage: менеджер источников
        """
        super().__init__()

        self.running = False
        self.source_manager = source_manage

        # Настройки для каждой камеры
        self.zones = {}
        self.frame_counters = {}

        self.detectors = {}
        self.zone_managers = {}
        self.alert_filters = {}

        # Для мониторинга
        self.last_log_time = time.time()
        self.debug_mode = False

        # Настройки по умолчанию
        self.model_name = "yolov8m.pt"
        self.confidence = 0.45
        self.watched_classes = {0, 1, 2, 3, 5, 7, 67}
        self.draw_rectangles = True
        self.min_presence_time = 2.0
        self.alert_cooldown = 30.0
        self.min_overlap_ratio = 0.1

        # Определяем устройство
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"VideoThread: Используется устройство: {self.device.upper()}")


    def init_source(self, source_id: int):
        """Инициализация источника для детекции"""
        if source_id in self.zones:
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

        print(f"VideoThread: Инициализация источника {source_id}")

        self.zones[source_id] = []
        self.frame_counters[source_id] = 0

        print(f"VideoThread: Источник {source_id} инициализирован")

    def update_zones(self, zones: list[tuple[int, int, int, int]], source_id: int):
        """
        Обновление зон
        :param zones: список зон [(x, y, w, h), ...]
        :param source_id: идентификатор источника
        """
        if source_id in self.zone_managers:
            self.zone_managers[source_id].set_zones(zones)
            self.alert_filters[source_id].reset()

            self.log_signal.emit(f"[Камера {source_id}] Обновлены зоны")

    def run(self):
        """Основной цикл обработки видео"""
        self.running = True
        self.log_signal.emit("Поток видео запущен")
        self.source_manager.connect_all()

        while self.running:
            start_time = time.time()

            active_source = self.source_manager.get_active_source()

            if active_source is None:
                time.sleep(0.1)
                continue

            source_id = active_source.source_id
            self.init_source(source_id)

            frame = active_source.get_last_frame()

            if frame is None:
                self.source_status_signal.emit(source_id, False)
                time.sleep(0.1)
                continue

            self.source_status_signal.emit(source_id, True)
            self.frame_counters[source_id] += 1

            objects, annotated_frame = self.detectors[source_id].detect(frame)

            zone_manager = self.zone_managers[source_id]
            min_overlap = self.min_overlap_ratio

            for obj in objects:
                bbox = obj.get('bbox')
                if bbox:
                    # Находим все зоны, с которыми пересекается объект
                    intersecting_zones = zone_manager.get_all_intersections(bbox, min_overlap)
                    if intersecting_zones:
                        obj['in_zone'] = True
                        obj['zone_index'] = intersecting_zones[0]  # первая зона
                    else:
                        obj['in_zone'] = False
                        obj['zone_index'] = None
                else:
                    obj['in_zone'] = False
                    obj['zone_index'] = None

            alert_filter = self.alert_filters[source_id]
            alert_zones = alert_filter.process_frame(objects, zone_manager)

            # Обработка тревог
            for zone_idx in alert_zones:
                zone_name = zone_manager.zone_names[zone_idx] if zone_idx < len(
                    zone_manager.zone_names) else f"Зона {zone_idx}"
                print(f"Тревога в зоне {zone_name} | Время: {time.strftime('%H:%M:%S')}")

            active_zones = set()
            for obj in objects:
                if obj.get('in_zone') and obj.get('zone_index') is not None:
                    active_zones.add(obj['zone_index'])

            processed_frame = annotated_frame.copy()

            if self.draw_rectangles:
                for i, (zx, zy, zw, zh) in enumerate(self.zones.get(source_id, [])):
                    if i in active_zones:
                        color = (0, 0, 255)
                        thickness = 3
                    else:
                        color = (0, 255, 0)
                        thickness = 2

                    cv2.rectangle(processed_frame, (zx, zy), (zx + zw, zy + zh), color, thickness)
                    cv2.putText(processed_frame, f"Zone {i}", (zx + 5, zy + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            self.frame_ready.emit(processed_frame.copy(), active_zones, objects, source_id)

            frame_time = time.time() - start_time
            target_frame_time = 1.0 / 60.0
            if frame_time < target_frame_time:
                time.sleep(target_frame_time - frame_time)

        self.log_signal.emit("Поток видео остановлен")

    def stop(self):
        """
        Остановка потока обработки видео
        """
        self.running = False
        if self.source_manager:
            self.source_manager.stop_all()
        self.wait()

    def get_zone_manager(self, source_id):
        """У каждой камеры свой список отслеживаемых зон"""
        if source_id in self.zone_managers:
            return self.zone_managers[source_id]
        return None