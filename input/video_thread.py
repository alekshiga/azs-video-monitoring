import cv2
import time
import numpy as np
import torch
import sys
import os
from PyQt6.QtCore import QThread, pyqtSignal

from input.source_manager import SourceManager


class VideoThread(QThread):
    """
    Поток видео для обработки
    """
    # Сигналы
    frame_ready = pyqtSignal(object, object, object, int)  # frame, active_zones, objects, source_id
    log_signal = pyqtSignal(str)
    source_status_signal = pyqtSignal(int, bool)  # source_id, connected

    def __init__(self, source_manage: SourceManager):
        """
        Инициализация потока обработки
        :param source_manage: менеджер источников
        """
        super().__init__()

        self.running = False
        self.source_manager = None

        # Настройки для каждой камеры
        self.zones = {}
        self.frame_counters = {}

        # Для мониторинга
        self.last_log_time = time.time()
        self.debug_mode = False

        # Настройки по умолчанию
        self.model_name = "yolov8m.pt"
        self.confidence = 0.45
        self.watched_classes = {0, 1, 2, 3, 5, 7, 67}

        # Определяем устройство
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"VideoThread: Используется устройство: {self.device.upper()}")


    def init_source(self, source_id: int):
        """
        Инициализация источника для детекции
        """
        if source_id in self.zones:
            return

        print(f"VideoThread: Инициализация источника {source_id}")

        self.zones[source_id] = []
        self.frame_counters[source_id] = 0

        print(f"VideoThread: Источник {source_id} инициализирован")

    def update_zones(self, zones, source_id: int):
        """
        Обновление зон
        :param zones: список зон [(x, y, w, h), ...]
        :param source_id: идентификатор источника
        """
        if source_id in self.zones:
            self.zones[source_id] = zones.copy()
            self.log_signal.emit(f"[Камера {source_id}] Обновлены зоны")

    def run(self):
        """
        Основной цикл обработки видео
        """
        self.running = True
        self.log_signal.emit("Поток видео запущен")
        self.source_manager.connect_all()

        frame_times = []

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

            processed_frame = frame
            active_zones = set()
            moving_objects = []

            # Отрисовка зон на кадре (опционально)
            # todo сделать чекбокс отрисовки зон
            for i, (zx, zy, zw, zh) in enumerate(self.zones.get(source_id, [])):
                cv2.rectangle(processed_frame, (zx, zy), (zx + zw, zy + zh), (0, 255, 0), 2)
                cv2.putText(processed_frame, f"Zone {i}", (zx + 5, zy + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Отправка кадра в главное окно
            self.frame_ready.emit(processed_frame.copy(), active_zones, moving_objects, source_id)

            current_time = time.time()
            if current_time - self.last_log_time >= 5.0:
                self.log_signal.emit(f"Кадров обработано: {self.frame_counters[source_id]}")
                self.last_log_time = current_time

            # Управление FPS (для множества камер уменьшаем fps)
            frame_time = time.time() - start_time
            frame_times.append(frame_time)
            if len(frame_times) > 30:
                frame_times.pop(0)

            target_frame_time = 1.0 / 60.0  # 60 FPS
            if frame_time < target_frame_time:
                time.sleep(target_frame_time - frame_time)

        self.log_signal.emit("Поток видео остановлен")