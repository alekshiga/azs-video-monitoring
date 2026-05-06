import cv2
import time
import numpy as np
import torch
import sys
import os
from PyQt6.QtCore import QThread, pyqtSignal


class VideoThread(QThread):
    """
    Поток видео для обработки
    """
    frame_ready = pyqtSignal(object, object, object, int)

    def __init__(self):
        super().__init__()
        self.running = False

        self.zones = {}

        # Настройки по умолчанию
        self.model_name = "yolov8m.pt"
        self.confidence = 0.45
        self.watched_classes = {0, 1, 2, 3, 5, 7, 67}

        # Определяем устройство
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"VideoThread: Используется устройство: {self.device.upper()}")

    