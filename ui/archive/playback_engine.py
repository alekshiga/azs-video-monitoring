"""
PlaybackThread — воспроизведение сегментов архива в отдельном потоке.

Декодирует MP4 через OpenCV (вне UI-потока), отдаёт кадры сигналом.
Позиция кадра = start_ts сегмента + смещение внутри файла, поэтому
playhead на таймлайне всегда показывает реальное время съёмки.
Непрерывность между сегментами обеспечивает ArchiveTab по сигналу
segment_finished.
"""

import time
import threading

import cv2
from PyQt6.QtCore import QThread, pyqtSignal


class PlaybackThread(QThread):
    frame_ready = pyqtSignal(object, float)   # BGR ndarray, epoch_ts
    position = pyqtSignal(float)              # epoch seconds
    segment_finished = pyqtSignal(float)     # epoch конца сегмента
    state_changed = pyqtSignal(bool)         # playing?

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._stop = False
        self._pending = None        # (segment, offset_ms)
        self._cap = None
        self._seg = None
        self._fps = 25.0
        self._playing = False
        self._speed = 1.0
        self._step = 0
        self._just_opened = False

    # --------------------- управление из UI-потока --------------------- #

    def open_at(self, segment, offset_ms=0.0, autoplay=True):
        with self._lock:
            self._pending = (segment, max(0.0, offset_ms))
            if autoplay:
                self._playing = True

    def play(self):
        with self._lock:
            self._playing = True
        self.state_changed.emit(True)

    def pause(self):
        with self._lock:
            self._playing = False
        self.state_changed.emit(False)

    def toggle(self):
        with self._lock:
            self._playing = not self._playing
            st = self._playing
        self.state_changed.emit(st)

    def set_speed(self, mult):
        with self._lock:
            self._speed = max(0.1, min(16.0, mult))

    def step(self, frames=1):
        with self._lock:
            self._playing = False
            self._step += frames
        self.state_changed.emit(False)

    def stop_playback(self):
        self._stop = True
        self.wait(2000)

    def is_playing(self):
        return self._playing

    # ----------------------------- поток ------------------------------- #

    def run(self):
        while not self._stop:
            pend = None
            with self._lock:
                if self._pending is not None:
                    pend = self._pending
                    self._pending = None
            if pend is not None:
                self._do_open(*pend)

            with self._lock:
                cap = self._cap
                playing = self._playing
                speed = self._speed
                do_step = self._step > 0
                just = self._just_opened
                self._just_opened = False

            if cap is None:
                self.msleep(20)
                continue

            if not playing and not do_step and not just:
                self.msleep(20)
                continue

            t_read = time.time()
            ret, frame = cap.read()
            if not ret or frame is None:
                # конец сегмента
                seg = self._seg
                end = (seg.get("end_ts") or
                       (seg.get("start_ts") + (seg.get("duration") or 0))) if seg else 0
                self._release()
                self.segment_finished.emit(end)
                continue

            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            epoch = self._seg["start_ts"] + pos_ms / 1000.0
            self.frame_ready.emit(frame, epoch)
            self.position.emit(epoch)

            if do_step:
                with self._lock:
                    self._step = max(0, self._step - 1)
                continue

            # тайминг по FPS с учётом скорости
            interval = (1.0 / self._fps) / max(0.1, speed)
            elapsed = time.time() - t_read
            sleep_s = interval - elapsed
            if sleep_s > 0:
                self.msleep(int(sleep_s * 1000))

        self._release()

    def _do_open(self, segment, offset_ms):
        self._release()
        try:
            cap = cv2.VideoCapture(segment["path"])
            if not cap.isOpened():
                return
            fps = cap.get(cv2.CAP_PROP_FPS)
            self._fps = fps if fps and fps > 0 else 25.0
            if offset_ms > 0:
                cap.set(cv2.CAP_PROP_POS_MSEC, offset_ms)
            with self._lock:
                self._cap = cap
                self._seg = segment
                self._just_opened = True
        except Exception:
            self._release()

    def _release(self):
        with self._lock:
            cap = self._cap
            self._cap = None
            self._seg = None
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
