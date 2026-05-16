import time
import cv2
import torch
from PyQt6.QtCore import QThread, pyqtSignal

from core.detection import MotionDetector
from core.zone_manager import ZoneManager
from core.alert_filter import AlertFilter
from core.scenario_analyzer import ScenarioAnalyzer
from input.source_manager import SourceManager


class VideoThread(QThread):
    all_frames_ready = pyqtSignal(list)
    log_signal = pyqtSignal(str)
    alert_signal = pyqtSignal(int, object, int)

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

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"VideoThread: {self.device.upper()}")

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

    def update_zones(self, zones, source_id):
        if source_id in self.zone_managers:
            self.zone_managers[source_id].set_zones(zones)
            self.alert_filters[source_id].reset()

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

                alert_zones = self.alert_filters[source_id].process_frame(objects, zone_manager)
                for zone_idx in alert_zones:
                    zone_name = zone_manager.zone_names[zone_idx] if zone_idx < len(zone_manager.zone_names) else f"Зона {zone_idx}"
                    self.alert_signal.emit(zone_idx, annotated_frame.copy(), source_id)

                current_time = time.time()
                scenario_alerts = self.scenario_analyzers[source_id].update(objects, current_time)
                for alert in scenario_alerts:
                    self.alert_signal.emit(-1, annotated_frame.copy(), source_id)

                active_zones = {obj['zone_index'] for obj in objects if obj.get('in_zone') and obj.get('zone_index') is not None}

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

    def get_zone_manager(self, source_id):
        return self.zone_managers.get(source_id)