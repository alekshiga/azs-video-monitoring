"""
SegmentIndexer — периодически сканирует каталоги архива, находит
финализированные сегменты и регистрирует их в БД.

"Финализированным" считается любой сегмент, кроме самого нового по камере
(самый новый ещё пишется ffmpeg). start_ts берётся из имени файла
(-strftime), end_ts/duration — из начала следующего сегмента, либо из mtime.
"""

import os
import threading
import time
from datetime import datetime

from .recorder import VIDEO_FILE_EXT  # noqa: F401  (единый список расширений)


def _parse_start_ts(path) -> float | None:
    """
    Путь .../cam{id}/YYYY-MM-DD/HH-MM-SS.mp4 -> локальная эпоха.
    """
    try:
        fname = os.path.splitext(os.path.basename(path))[0]   # HH-MM-SS
        day = os.path.basename(os.path.dirname(path))          # YYYY-MM-DD
        dt = datetime.strptime(f"{day} {fname}", "%Y-%m-%d %H-%M-%S")
        return dt.timestamp()
    except Exception:
        return None


class SegmentIndexer:
    def __init__(self, db, archive_dir, settings, log_cb=None):
        self.db = db
        self.archive_dir = archive_dir
        self.settings = settings
        self.log_cb = log_cb or (lambda msg: None)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="seg-indexer")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as e:
                self.log_cb(f"Индексатор архива: ошибка {e}")
            self._stop.wait(self.settings.indexer_poll_seconds)

    def _camera_dirs(self):
        if not os.path.isdir(self.archive_dir):
            return
        for name in os.listdir(self.archive_dir):
            if not name.startswith("cam"):
                continue
            try:
                sid = int(name[3:])
            except ValueError:
                continue
            yield sid, os.path.join(self.archive_dir, name)

    def _collect_segments(self, cam_dir):
        """Список (path, start_ts) всех mp4 камеры, отсортирован по времени."""
        found = []
        if not os.path.isdir(cam_dir):
            return found
        for day in os.listdir(cam_dir):
            day_path = os.path.join(cam_dir, day)
            if not os.path.isdir(day_path):
                continue
            for fn in os.listdir(day_path):
                if not fn.lower().endswith(".mp4"):
                    continue
                p = os.path.join(day_path, fn)
                ts = _parse_start_ts(p)
                if ts is not None:
                    found.append((p, ts))
        found.sort(key=lambda x: x[1])
        return found

    def scan_once(self) -> int:
        """Индексирует новые финализированные сегменты. Возвращает их число."""
        seg_len = self.settings.segment_seconds
        total_new = 0

        for sid, cam_dir in self._camera_dirs():
            segs = self._collect_segments(cam_dir)
            if len(segs) < 2:
                continue  # 0-1 файлов: единственный — ещё пишется

            known = self.db.segment_paths(sid)
            # последний файл — текущий (пишется), его пропускаем
            finalized = segs[:-1]

            for i, (path, start_ts) in enumerate(finalized):
                if path in known:
                    continue
                next_start = segs[i + 1][1]
                duration = self._estimate_duration(path, start_ts, next_start, seg_len)
                end_ts = start_ts + duration
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = None
                rid = self.db.insert_segment(sid, path, start_ts, end_ts,
                                             duration, size)
                if rid:
                    total_new += 1

        if total_new:
            self.log_cb(f"Архив: проиндексировано сегментов: {total_new}")
        return total_new

    @staticmethod
    def _estimate_duration(path, start_ts, next_start, seg_len) -> float:
        # непрерывная запись: длительность = начало следующего − начало текущего
        gap = next_start - start_ts
        if 0 < gap <= seg_len * 2:
            return gap
        # был разрыв записи: оценим по времени модификации файла
        try:
            mtime = os.path.getmtime(path)
            d = mtime - start_ts
            if 0 < d <= seg_len * 2:
                return d
        except OSError:
            pass
        return float(seg_len)
