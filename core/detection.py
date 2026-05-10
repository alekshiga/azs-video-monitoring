import time

import cv2
import torch
from ultralytics import YOLO


def _overlap_ratio(rect1: tuple[int, int, int, int], rect2: tuple[int, int, int, int]) -> float:
    """
    Процент пересечения прямоугольников, чтобы не учитывать мелкие пересечения
    :return: отношение площади пересечения к площади прямоугольника 1
    """
    x1 = max(rect1[0], rect2[0])
    y1 = max(rect1[1], rect2[1])
    x2 = min(rect1[2], rect2[2])
    y2 = min(rect1[3], rect2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (rect1[2] - rect1[0]) * (rect1[3] - rect1[1])

    return intersection / max(area1, 1)


def _rect_intersects(rect1: tuple[int, int, int, int], rect2: tuple[int, int, int, int]) -> bool:
    """
    Проверяем пересечение двух прямоугольников
    :return: True если пересекаются, иначе False
    """
    if rect1[2] <= rect2[0] or rect2[2] <= rect1[0] or rect1[3] <= rect2[1] or rect2[3] <= rect1[1]:
        return False
    return True


class MotionDetector:
    """
    Детектор движения на основе YOLOv8,
    каждый объект получает уникальный ID, класс, траекторию
    """

    # Классы COCO которые нас интересуют (для АЗС)
    WATCHED_CLASSES = {
        0: "person",
        1: "bicycle",
        2: "car",
        3: "motorcycle",
        5: "bus",
        7: "truck",
        67: "phone",
    }

    # Цвета для разных классов (BGR)
    CLASS_COLORS = {
        0: (0, 255, 128),  # person — зелёный
        1: (255, 200, 0),  # bicycle — голубой
        2: (255, 128, 0),  # car — синий
        3: (0, 200, 255),  # motorcycle — оранжевый
        5: (255, 0, 128),  # bus — розовый
        7: (128, 0, 255),  # truck — фиолетовый
        67: (0, 255, 255),  # phone - жёлтый
    }

    def __init__(self, model_name="yolov8m.pt", confidence=0.5, device=None,
                 watched_classes = None, draw_rectangles=True):
        """
        Инициализация детектора движения
        :param model_name: имя файла модели YOLO
        :param confidence: минимальная уверенность детекции (0.0 - 1.0)
        :param device: устройство для вычислений ('cuda', 'cpu' или None для автоопределения)
        :param draw_rectangles: отрисовывать рамки и зоны на кадре
        """

        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        print(self.device)
        self.model = YOLO(model_name)
        if self.device == "cuda":
            self.model.to("cuda")

        self.draw_rectangles = draw_rectangles

        self.watched_classes = watched_classes or {0, 2, 5, 7}

        # Параметры обнаружения
        self.confidence = confidence
        self.frame_count = 0
        self.detection_time = 0.0

        # История траекторий
        self.trajectories = {}
        self.max_trajectory_length = 50

        # Время первого обнаружения
        self.track_first_seen = {}

        # Время последнего обнаружения (для очистки старых треков)
        self.track_last_seen = {}
        self.track_timeout = 3.0

    def detect(self, frame, forbidden_zones: list[tuple[int, int, int, int]] | None = None):
        """
        Детекция + трекинг из YOLO
        :param frame: кадр
        :param forbidden_zones: список отслеживаемых зон
        :return: список обнаруженных объектов и аннотированный кадр
        """
        if forbidden_zones is None:
            forbidden_zones = []

        self.frame_count += 1
        current_time = time.time()

        start_time = time.time()

        # YOLO + ByteTrack
        """
        args: source - источник изображения,
        persist говорит о том, что это следующее изображение после предыдущего,
        и стоит ожидать объекты с прошлого изображения,
        classes - отслеживаемые классы,
        confidence - порог уверенности,
        iou (Intersection over Union) - это метрика, которая показывает, насколько сильно два прямоугольника пересекаются.
        то есть алгоритм может нарисовать 5 рамок вокруг одного и того же объекта, этот порог удалит лишние рамки,
        оставив одну с самой высокой уверенностью, выберем 0.5, т.к. на АЗС нам нужно различать крупные, непересекающиеся объекты
        tracker - модель трекера, по дефолту BoT-SORT - botsort.yaml, но выберем ByteTrack - bytetrack.yaml
        verbose это параметр, который включает или отключает подробные сообщения в консоль.
        """
        results = self.model.track(
            frame,
            persist=True,
            classes=list(self.WATCHED_CLASSES.keys()),
            conf=self.confidence,
            iou=0.5,
            tracker="bytetrack.yaml",
            verbose=False,
            device=self.device,
        )

        self.detection_time = time.time() - start_time

        moving_objects: list[dict] = []
        active_tracks: set[int] = set()

        if results is not None and len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            xyxy = boxes.xyxy.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            cls = boxes.cls.cpu().numpy()
            ids = boxes.id.cpu().numpy() if boxes.id is not None else None

            for i in range(len(boxes)):
                # Координаты
                x1, y1, x2, y2 = xyxy[i].astype(int)
                w = x2 - x1
                h = y2 - y1
    
                # Класс
                cls_id = int(cls[i])
                cls_name = self.WATCHED_CLASSES.get(cls_id, f"class_{cls_id}")
    
                # Track ID
                track_id = None
                if ids is not None:
                    track_id = int(ids[i])
                    active_tracks.add(track_id)
    
                    # Обновляем траекторию
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
    
                    if track_id not in self.trajectories:
                        self.trajectories[track_id] = []
                        self.track_first_seen[track_id] = current_time
    
                    self.trajectories[track_id].append((center_x, center_y))
                    self.track_last_seen[track_id] = current_time
    
                    # Ограничиваем длину траектории
                    if len(self.trajectories[track_id]) > self.max_trajectory_length:
                        self.trajectories[track_id] = \
                            self.trajectories[track_id][-self.max_trajectory_length:]
    
                # Проверяем пересечение с запретными зонами
                in_zone = False
                zone_index = None
    
                for zi, (zx, zy, zw, zh) in enumerate(forbidden_zones):
                    if _rect_intersects(
                            (x1, y1, x2, y2),
                            (zx, zy, zx + zw, zy + zh)
                    ):
                        # Считаем долю пересечения
                        overlap = _overlap_ratio(
                            (x1, y1, x2, y2),
                            (zx, zy, zx + zw, zy + zh)
                        )
                        if overlap > 0.1:  # минимум 10% пересечения
                            in_zone = True
                            zone_index = zi
                            break
    
                # Время в кадре
                time_tracked = 0
                if track_id and track_id in self.track_first_seen:
                    time_tracked = current_time - self.track_first_seen[track_id]
    
                moving_objects.append({
                    'bbox': (x1, y1, w, h),
                    'in_zone': in_zone,
                    'zone_index': zone_index,
                    'area': w * h,
                    'track_id': track_id,
                    'class_id': cls_id,
                    'class_name': cls_name,
                    'confidence': float(conf[i]),
                    'time_tracked': time_tracked,
                })

        # Очищаем старые треки
        self._cleanup_old_tracks(current_time, active_tracks)

        # Отрисовка
        annotated_frame = frame.copy()
        if self.draw_rectangles:
            self._draw_frame(annotated_frame, moving_objects, forbidden_zones)

        return moving_objects, annotated_frame

    def _cleanup_old_tracks(self, current_time, active_ids):
        """
        Удаление треков которые давно не обновлялись
        :param current_time: текущее время в секундах
        :param active_ids: множество активных идентификаторов треков
        """
        expired = []
        for tid, last_seen in self.track_last_seen.items():
            if tid not in active_ids and \
                    (current_time - last_seen) > self.track_timeout:
                expired.append(tid)

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
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)

            # Метка
            id_str = f"#{track_id}" if track_id is not None else ""
            time_str = f"{time_tracked:.0f}с" if time_tracked > 1 else ""
            label = f"{cls_name}{id_str} {conf:.0%} {time_str}"

            if obj['in_zone']:
                label = f"Тревога {label} Зона {obj['zone_index']}"

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
        """
        Сброс состояния трекера
        :return:
        """
        self.trajectories.clear()
        self.track_first_seen.clear()
        self.track_last_seen.clear()
        self.frame_count = 0