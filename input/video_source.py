import cv2
import threading
import time

from collections import deque

class VideoSource:
    """
    Источник видео: USB-камера или IP-камера (RTSP)
    """

    def __init__(self, source_id: int, name: str, source_path: str):
        """
        инициализация источника
        :param source_id: идентификатор
        :param name: название
        :param source_path: путь к источнику
        """
        self._thread = None
        self.source_id = source_id
        self.name = name
        self.source_path = source_path
        self.cap = None
        self.is_connected = False
        self.last_frame = None
        self._lock = threading.Lock()
        self._running = False
        self._Thread = None
        self.fps = 60
        self.frame_buffer = deque(maxlen=2)
        self.zones_file = f"config/zones_cam_{source_id}.json"

    def connect(self) -> bool:
        """
        Подключение к источнику
        :return: True если подключено успешно, иначе False
        """
        try:
            if self.cap:
                self.cap.release()

            if isinstance(self.source_path, int):
                # USB-камера
                self.cap = cv2.VideoCapture(self.source_path)
                print(f"[{self.name}] Подключение к USB камере (индекс: {self.source_path})")
            elif isinstance(self.source_path, str) and self.source_path.startswith("rtsp://"):
                # IP-камера (RTSP)
                self.cap = cv2.VideoCapture(self.source_path)
                print(f"[{self.name}] Подключение к IP-камере (RTSP): {self.source_path[:50]}...")
            else:
                print(f"[{self.name}] Ошибка: неподдерживаемый тип источника (только USB камера или RTSP)")
                return False

            if self.cap and self.cap.isOpened():
                self.is_connected = True

                self.fps = self.cap.get(cv2.CAP_PROP_FPS)
                if self.fps <= 0:
                    self.fps = 60

                print(f"[{self.name}] Подключен (FPS: {self.fps:.1f})")
                return True

            else:
                print(f"[{self.name}] Ошибка подключения")
                self.is_connected = False
                return False

        except Exception as e:
            print(f"[{self.name}] Ошибка: {e}")
            self.is_connected = False
            return False

    def start_capture(self):
        """
        Запуск захвата видео
        """
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"[{self.name}] Запущен поток захвата")

    def _capture_loop(self):
        """
        Цикл захвата кадров
        """
        while self._running:
            if not self.is_connected:
                time.sleep(1)
                self.connect()
                continue

            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()

                if ret and frame is not None:
                    with self._lock:
                        self.frame_buffer.append(frame.copy())

                else:
                    self.is_connected = False
                    print(f"[{self.name}] Потеря соединения с камерой")
            time.sleep(0.01)

    def get_last_frame(self):
        """
        Получение последнего кадра из буфера
        :return: ndarray или же None
        """
        with self._lock:
            if self.frame_buffer:
                return self.frame_buffer[-1].copy()
            if self.last_frame:
                return self.last_frame.copy()
        return None

    def stop(self):
        """
        Остановка захвата, освобождение ресурсов
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        if self.cap:
            self.cap.release()
            print(f"[{self.name}] Остановлен")

    def get_stats(self):
        """
        :return: Словарь со статистикой
        """
        return {
            'id': self.source_id,
            'name': self.name,
            'connected': self.is_connected,
            'fps': self.fps,
            'path': self.source_path
        }