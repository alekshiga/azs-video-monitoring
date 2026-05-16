import time
import cv2
import torch
from ultralytics import YOLO


def _overlap_ratio(rect1, rect2):
    x1, y1, x2, y2 = max(rect1[0], rect2[0]), max(rect1[1], rect2[1]), min(rect1[2], rect2[2]), min(rect1[3], rect2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    intersection = (x2 - x1) * (y2 - y1)
    area1 = (rect1[2] - rect1[0]) * (rect1[3] - rect1[1])
    return intersection / max(area1, 1)


def _rect_intersects(rect1, rect2):
    return not (rect1[2] <= rect2[0] or rect2[2] <= rect1[0] or rect1[3] <= rect2[1] or rect2[3] <= rect1[1])


class MotionDetector:
    WATCHED_CLASSES = {0: "person", 2: "car", 5: "bus", 7: "truck"}
    CLASS_COLORS = {
        0: (0, 255, 0),
        2: (255, 128, 0),
        5: (255, 0, 128),
        7: (128, 0, 255)
    }

    def __init__(self, model_name="yolov8m.pt", confidence=0.5, device=None, watched_classes=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = YOLO(model_name)
        self.draw_rectangles = True
        self.watched_classes = watched_classes or {0, 2, 5, 7}
        self.confidence = confidence
        self.frame_count = 0
        self.trajectories = {}
        self.max_trajectory_length = 50
        self.track_first_seen = {}
        self.track_last_seen = {}
        self.track_timeout = 3.0

    def detect(self, frame, forbidden_zones=None):
        if forbidden_zones is None:
            forbidden_zones = []

        self.frame_count += 1
        current_time = time.time()

        results = self.model.track(
            frame, persist=True,
            classes=list(self.WATCHED_CLASSES.keys()),
            conf=self.confidence, iou=0.5,
            tracker="bytetrack.yaml", verbose=False, device=self.device
        )

        moving_objects = []
        active_tracks = set()

        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            xyxy = boxes.xyxy.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            cls = boxes.cls.cpu().numpy()
            ids = boxes.id.cpu().numpy() if boxes.id is not None else None

            for i in range(len(boxes)):
                x1, y1, x2, y2 = xyxy[i].astype(int)
                w, h = x2 - x1, y2 - y1
                cls_id = int(cls[i])
                cls_name = self.WATCHED_CLASSES.get(cls_id, f"class_{cls_id}")

                track_id = None
                if ids is not None:
                    track_id = int(ids[i])
                    active_tracks.add(track_id)
                    center = ((x1 + x2) // 2, (y1 + y2) // 2)
                    if track_id not in self.trajectories:
                        self.trajectories[track_id] = []
                        self.track_first_seen[track_id] = current_time
                    self.trajectories[track_id].append(center)
                    self.track_last_seen[track_id] = current_time
                    if len(self.trajectories[track_id]) > self.max_trajectory_length:
                        self.trajectories[track_id] = self.trajectories[track_id][-self.max_trajectory_length:]

                in_zone = False
                zone_index = None
                for zi, (zx, zy, zw, zh) in enumerate(forbidden_zones):
                    if _rect_intersects((x1, y1, x2, y2), (zx, zy, zx + zw, zy + zh)):
                        if _overlap_ratio((x1, y1, x2, y2), (zx, zy, zx + zw, zy + zh)) > 0.1:
                            in_zone = True
                            zone_index = zi
                            break

                time_tracked = current_time - self.track_first_seen[track_id] if track_id and track_id in self.track_first_seen else 0

                moving_objects.append({
                    'bbox': (x1, y1, w, h), 'in_zone': in_zone, 'zone_index': zone_index,
                    'area': w * h, 'track_id': track_id, 'class_id': cls_id,
                    'class_name': cls_name, 'confidence': float(conf[i]), 'time_tracked': time_tracked
                })

        self._cleanup_old_tracks(current_time, active_tracks)
        annotated_frame = frame.copy()
        if self.draw_rectangles:
            self._draw_frame(annotated_frame, moving_objects, forbidden_zones)

        return moving_objects, annotated_frame

    def _cleanup_old_tracks(self, current_time, active_ids):
        expired = [tid for tid, last_seen in self.track_last_seen.items() if tid not in active_ids and current_time - last_seen > self.track_timeout]
        for tid in expired:
            self.trajectories.pop(tid, None)
            self.track_first_seen.pop(tid, None)
            self.track_last_seen.pop(tid, None)

    def _draw_frame(self, frame, objects, zones):
        """
        Отрисовка зон, объектов и траекторий на кадре
        :param frame: кадр для отрисовки (модифицируется на месте)
        :param objects: список обнаруженных объектов
        :param zones: список запрещённых зон для отрисовки
        :return:
        """
        # Отслеживаемые зоны
        """
        for i, (zx, zy, zw, zh) in enumerate(zones):
            # Полупрозрачная заливка
            overlay = frame.copy()
            cv2.rectangle(overlay, (zx, zy), (zx + zw, zy + zh), (0, 100, 255), -1)
            cv2.addWeighted(overlay, 0.12, frame, 0.88, 0, frame)

            # Рамка
            cv2.rectangle(frame, (zx, zy), (zx + zw, zy + zh), (0, 150, 255), 2)

            # Название
            label = f"Зона {i}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (zx, zy - th - 10), (zx + tw + 8, zy), (0, 150, 255), -1)
            cv2.putText(frame, label, (zx + 4, zy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        """
        # Объекты
        for obj in objects:
            x, y, w, h = obj['bbox']
            track_id = obj.get('track_id')
            cls_name = obj.get('class_name', '?')
            conf = obj.get('confidence', 0)
            time_tracked = obj.get('time_tracked', 0)
            cls_id = obj.get('class_id', 0)

            # Цвет по классу
            base_color = self.CLASS_COLORS.get(cls_id, (0, 255, 0))

            if obj['in_zone']:
                color = (0, 0, 255)
                thickness = 3
                # Красная заливка если есть движение в зоне
                overlay = frame.copy()
                cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 255), -1)
                cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
            else:
                color = base_color
                thickness = 2

            # Рамка объекта
            #cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)

            # Метка
            id_str = f"#{track_id}" if track_id is not None else ""
            time_str = f"{time_tracked:.0f}s" if time_tracked > 1 else ""
            label = f"{cls_name}{id_str} {conf:.0%} {time_str}"

            if obj['in_zone']:
                label = f"ALERT {label} Zone {obj['zone_index']}"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(frame, (x, y - th - 10), (x + tw + 6, y), color, -1)
            cv2.putText(frame, label, (x + 3, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            # Траектория
            if track_id and track_id in self.trajectories:
                points = self.trajectories[track_id]
                if len(points) > 1:
                    for j in range(1, len(points)):
                        alpha = j / len(points)
                        pt_color = tuple(int(c * alpha) for c in color)
                        cv2.line(frame, points[j - 1], points[j], pt_color, 2)

    def reset(self):
        self.trajectories.clear()
        self.track_first_seen.clear()
        self.track_last_seen.clear()
        self.frame_count = 0