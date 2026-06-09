"""
RetentionSweeper — следит, чтобы архив не переполнил диск.

Политика на каждом проходе:
  1. По возрасту: удалить сегменты старше max_age_days.
  2. По размеру: пока суммарный размер архива > max_gb — удалять самые старые.
  3. По свободному месту: пока свободно на диске < min_free_gb — удалять старые.

Удаление: файл + запись в БД + чистка опустевших каталогов дня.
Работает на отдельном таймере, чтобы очистка шла ДО заполнения диска.
"""

import os
import shutil
import threading
import time


class RetentionSweeper:
    def __init__(self, db, archive_dir, settings, log_cb=None):
        self.db = db
        self.archive_dir = archive_dir
        self.settings = settings
        self.log_cb = log_cb or (lambda msg: None)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="retention")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        # первый проход — почти сразу после старта
        self._stop.wait(10)
        while not self._stop.is_set():
            try:
                n = self.sweep_once()
                if n:
                    self.log_cb(f"Архив: удалено старых сегментов: {n}")
            except Exception as e:
                self.log_cb(f"Очистка архива: ошибка {e}")
            self._stop.wait(self.settings.retention_poll_seconds)

    def _delete(self, seg) -> bool:
        path = seg.get("path")
        try:
            if path and os.path.exists(path):
                os.remove(path)
            self.db.delete_segment(seg["id"])
            # удаляем опустевший каталог дня
            day_dir = os.path.dirname(path) if path else None
            if day_dir and os.path.isdir(day_dir) and not os.listdir(day_dir):
                os.rmdir(day_dir)
            return True
        except OSError as e:
            self.log_cb(f"Архив: не удалось удалить {path}: {e}")
            return False

    def _free_gb(self) -> float:
        try:
            return shutil.disk_usage(self.archive_dir).free / (1024 ** 3)
        except OSError:
            return float("inf")

    def sweep_once(self) -> int:
        s = self.settings
        deleted = 0

        # 1) по возрасту
        if s.max_age_days and s.max_age_days > 0:
            cutoff = time.time() - s.max_age_days * 86400
            for seg in self.db.segments_older_than(cutoff, limit=1000):
                if self._stop.is_set():
                    return deleted
                if self._delete(seg):
                    deleted += 1

        # 2) по суммарному размеру
        if s.max_gb and s.max_gb > 0:
            limit_bytes = s.max_gb * (1024 ** 3)
            while self.db.total_archive_bytes() > limit_bytes:
                if self._stop.is_set():
                    return deleted
                batch = self.db.oldest_segments(limit=50)
                if not batch:
                    break
                for seg in batch:
                    if self.db.total_archive_bytes() <= limit_bytes:
                        break
                    if self._delete(seg):
                        deleted += 1

        # 3) по свободному месту на диске
        if s.min_free_gb and s.min_free_gb > 0:
            guard = 0
            while self._free_gb() < s.min_free_gb and guard < 10000:
                if self._stop.is_set():
                    return deleted
                batch = self.db.oldest_segments(limit=50)
                if not batch:
                    break
                for seg in batch:
                    if self._delete(seg):
                        deleted += 1
                    guard += 1

        return deleted
