"""
SegmentRecorder — надзор за одним процессом ffmpeg, который пишет оригинальный
поток камеры сегментами по ~60с (без перекодирования, -c copy).

Особенности для продакшна 24/7:
- отдельный процесс ОС на камеру: тяжёлый I/O не блокирует Python/Qt;
- supervisor-поток: перезапуск ffmpeg при падении с экспоненциальным backoff;
- stderr-drain поток: труба ffmpeg не переполняется, ведётся heartbeat;
- "dir keeper": заранее создаёт каталоги текущей и следующей даты
  (ffmpeg с -strftime сам подкаталоги не создаёт), чтобы переход через
  полночь не прерывал запись;
- graceful stop: посылаем 'q' в stdin, чтобы текущий сегмент корректно
  финализировался (валидный moov), затем terminate/kill.
"""

import os
import subprocess
import threading
import time
from datetime import datetime, timedelta

from .ffmpeg_locator import ffmpeg_exe

VIDEO_FILE_EXT = ('.mp4', '.avi', '.mov', '.mkv')


def _is_rtsp(path) -> bool:
    return isinstance(path, str) and path.lower().startswith("rtsp://")


def _is_file(path) -> bool:
    return isinstance(path, str) and path.lower().endswith(VIDEO_FILE_EXT)


def can_record(source_path) -> bool:
    """Запись поддерживается для RTSP и видеофайлов (USB пока не пишем)."""
    return _is_rtsp(source_path) or _is_file(source_path)


class SegmentRecorder:
    def __init__(self, source_id, name, source_path, cam_dir, settings, log_cb=None):
        self.source_id = source_id
        self.name = name
        self.source_path = source_path
        self.cam_dir = cam_dir
        self.settings = settings
        self.log_cb = log_cb or (lambda msg: None)

        self._proc = None
        self._stop = threading.Event()
        self._supervisor = None
        self._stderr_thread = None
        self._heartbeat = 0.0
        self._started_at = None

    # ------------------------------------------------------------------ #

    def start(self):
        if not can_record(self.source_path):
            self.log_cb(f"Камера {self.name}: запись недоступна для этого источника")
            return False
        if ffmpeg_exe() is None:
            self.log_cb(f"Камера {self.name}: ffmpeg не найден, запись отключена")
            return False
        os.makedirs(self.cam_dir, exist_ok=True)
        self._stop.clear()
        self._supervisor = threading.Thread(target=self._run, daemon=True,
                                             name=f"rec-{self.source_id}")
        self._supervisor.start()
        return True

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def gap_since(self):
        """
        Секунд с момента последней записи на диск. None — если данных пока нет.
        Опираемся на mtime самого свежего файла (надёжнее stderr, который при
        исправном потоке молчит). Большое значение => ffmpeg завис.
        """
        if not self.is_alive():
            return None
        newest = self._newest_mtime()
        if newest is None:
            return None
        return max(0.0, time.time() - newest)

    def _newest_mtime(self):
        latest = None
        try:
            for day in os.listdir(self.cam_dir):
                day_path = os.path.join(self.cam_dir, day)
                if not os.path.isdir(day_path):
                    continue
                for fn in os.listdir(day_path):
                    if fn.lower().endswith(".mp4"):
                        m = os.path.getmtime(os.path.join(day_path, fn))
                        if latest is None or m > latest:
                            latest = m
        except OSError:
            pass
        return latest

    # ------------------------------------------------------------------ #

    def _ensure_date_dirs(self):
        """Создаёт каталоги сегодняшней и завтрашней даты заранее."""
        now = datetime.now()
        for d in (now, now + timedelta(days=1)):
            try:
                os.makedirs(os.path.join(self.cam_dir, d.strftime("%Y-%m-%d")),
                            exist_ok=True)
            except OSError:
                pass

    def _build_cmd(self):
        out_template = os.path.join(self.cam_dir, "%Y-%m-%d", "%H-%M-%S.mp4")
        ff = ffmpeg_exe()
        cmd = [ff, "-hide_banner", "-loglevel", "warning"]

        if _is_rtsp(self.source_path):
            cmd += ["-rtsp_transport", "tcp", "-rw_timeout", "5000000",
                    "-i", self.source_path]
        else:  # видеофайл — имитируем живой поток зацикливанием (для отладки)
            cmd += ["-re", "-stream_loop", "-1", "-i", self.source_path]

        # без звука по умолчанию (-an); иначе копируем аудио как есть
        cmd += ["-an"] if not self.settings.record_audio else ["-c:a", "copy"]

        cmd += [
            "-c:v", "copy",                 # без перекодирования видео
            "-f", "segment",
            "-segment_time", str(self.settings.segment_seconds),
            "-segment_format", "mp4",
            "-segment_atclocktime", "1",    # резка по границам минут
            "-reset_timestamps", "1",       # каждый сегмент с PTS=0 -> seek в плеере
            "-strftime", "1",
            out_template,
        ]
        return cmd

    def _run(self):
        attempt = 0
        backoff = self.settings.restart_backoff
        while not self._stop.is_set():
            self._ensure_date_dirs()
            cmd = self._build_cmd()
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as e:
                self.log_cb(f"Камера {self.name}: не удалось запустить запись: {e}")
                if self._stop.wait(backoff[min(attempt, len(backoff) - 1)]):
                    break
                attempt += 1
                continue

            self._started_at = time.time()
            self._heartbeat = time.time()
            self.log_cb(f"Камера {self.name}: запись в архив начата")
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr, args=(self._proc,), daemon=True)
            self._stderr_thread.start()

            # "dir keeper" + ожидание процесса
            while not self._stop.is_set():
                self._ensure_date_dirs()
                try:
                    self._proc.wait(timeout=20)
                    break  # процесс завершился
                except subprocess.TimeoutExpired:
                    continue

            if self._stop.is_set():
                self._graceful_stop()
                break

            # процесс упал сам — перезапуск с backoff
            code = self._proc.returncode
            uptime = time.time() - (self._started_at or time.time())
            if uptime > 120:
                attempt = 0  # долго проработал — сбрасываем счётчик
            wait_s = backoff[min(attempt, len(backoff) - 1)]
            self.log_cb(f"Камера {self.name}: запись прервана (код {code}), "
                        f"перезапуск через {wait_s}с")
            if self._stop.wait(wait_s):
                break
            attempt += 1

    def _drain_stderr(self, proc):
        try:
            for line in iter(proc.stderr.readline, b""):
                if not line:
                    break
                self._heartbeat = time.time()
                text = line.decode("utf-8", "replace").strip()
                if text and ("error" in text.lower() or "fail" in text.lower()):
                    self.log_cb(f"Камера {self.name} [ffmpeg]: {text}")
        except Exception:
            pass

    def _graceful_stop(self):
        proc = self._proc
        if not proc or proc.poll() is not None:
            return
        try:
            # 'q' -> ffmpeg завершает мьюксер, текущий сегмент валиден
            proc.stdin.write(b"q")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    def stop(self):
        self._stop.set()
        if self._supervisor and self._supervisor.is_alive():
            self._supervisor.join(timeout=12)
        # на всякий случай
        if self.is_alive():
            try:
                self._proc.kill()
            except Exception:
                pass
