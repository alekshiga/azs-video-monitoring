import os
import cv2
import threading
import time
from collections import deque

from app_paths import user_data_path

os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000"
)


class VideoSource:
    def __init__(self, source_id: int, name: str, source_path: str, anpr=False):
        self._thread = None
        self.source_id = source_id
        self.name = name
        self.source_path = source_path
        self.anpr = anpr
        self.cap = None
        self.is_connected = False
        self.last_frame = None
        self._lock = threading.Lock()
        self._running = False
        self.fps = 60
        self.frame_buffer = deque(maxlen=2)
        self.zones_file = user_data_path("config", f"zones_cam_{source_id}.json")
        self.is_file = (
            isinstance(source_path, str)
            and source_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
        )

    def connect(self) -> bool:
        try:
            if self.cap:
                self.cap.release()

            if isinstance(self.source_path, int):
                self.cap = cv2.VideoCapture(self.source_path)
                print(f"[{self.name}] Подключение к USB камере (индекс: {self.source_path})")
            elif isinstance(self.source_path, str) and self.source_path.startswith("rtsp://"):
                self.cap = cv2.VideoCapture(self.source_path, cv2.CAP_FFMPEG)
                print(f"[{self.name}] Подключение к IP-камере (RTSP): {self.source_path[:50]}...")
            elif isinstance(self.source_path, str) and self.source_path.endswith(('.mp4', '.avi', '.mov', '.mkv')):
                self.cap = cv2.VideoCapture(self.source_path)
                print(f"[{self.name}] Подключение к видеофайлу: {self.source_path}")
            else:
                print(f"[{self.name}] Ошибка: неподдерживаемый тип источника")
                return False

            if self.cap and self.cap.isOpened():
                self.is_connected = True
                self.fps = self.cap.get(cv2.CAP_PROP_FPS)
                if self.fps <= 0:
                    # для файла 25, для камеры 60
                    self.fps = 25.0 if self.is_file else 60.0
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
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"[{self.name}] Запущен поток захвата")

    def _capture_loop(self):
        reconnect_cooldown = 10.0   # секунд между попытками переподключения
        last_reconnect_attempt = 0.0
        self.reconnect_attempts = 0

        while self._running:
            if not self.is_connected:
                now = time.time()
                if now - last_reconnect_attempt >= reconnect_cooldown:
                    last_reconnect_attempt = now
                    self.reconnect_attempts += 1
                    print(f"[{self.name}] Попытка переподключения #{self.reconnect_attempts}...")
                    if self.connect():
                        self.reconnect_attempts = 0
                time.sleep(1)
                continue

            if self.cap and self.cap.isOpened():
                frame_start = time.time()
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self._lock:
                        self.frame_buffer.append(frame.copy())

                    if self.is_file:
                        # НА ФАЙЛЕ ВЫСТАВЛЯЕМ 30 ФПС
                        target = 1.0 / self.fps if self.fps > 0 else 1.0 / 25.0
                        elapsed = time.time() - frame_start
                        if elapsed < target:
                            time.sleep(target - elapsed)
                    else:
                        time.sleep(0.01)
                elif self.is_file:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.01)
                else:
                    self.is_connected = False
                    print(f"[{self.name}] Потеря соединения")
                    time.sleep(0.01)
            else:
                time.sleep(0.01)

    def get_last_frame(self):
        with self._lock:
            if self.frame_buffer:
                return self.frame_buffer[-1].copy()
            if self.last_frame:
                return self.last_frame.copy()
        return None

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        if self.cap:
            self.cap.release()
            print(f"[{self.name}] Остановлен")

    def get_stats(self):
        return {
            'id': self.source_id,
            'name': self.name,
            'connected': self.is_connected,
            'fps': self.fps,
            'path': self.source_path
        }