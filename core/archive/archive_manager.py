"""
ArchiveManager — фасад подсистемы архива.

Владеет рекордерами (по камере), индексатором и очисткой; даёт UI единый
API для запросов к архиву (таймлайн/воспроизведение). Это обычный объект
с фоновыми потоками — не QThread, чтобы не нагружать ни цикл Qt, ни
аналитический VideoThread.
"""

import os
import threading

from . import settings as archive_settings
from .ffmpeg_locator import has_ffmpeg
from .recorder import SegmentRecorder, can_record
from .indexer import SegmentIndexer
from .retention import RetentionSweeper


class ArchiveManager:
    def __init__(self, source_manager, db, settings=None, log_cb=None):
        self.source_manager = source_manager
        self.db = db
        self.settings = settings or archive_settings.load()
        self.log_cb = log_cb or (lambda msg: None)

        self.archive_dir = self.settings.archive_dir
        os.makedirs(self.archive_dir, exist_ok=True)

        self.recorders = {}
        self._lock = threading.Lock()
        self.indexer = SegmentIndexer(db, self.archive_dir, self.settings, log_cb=self.log_cb)
        self.retention = RetentionSweeper(db, self.archive_dir, self.settings, log_cb=self.log_cb)
        self._started = False

    def set_log_cb(self, cb):
        self.log_cb = cb
        self.indexer.log_cb = cb
        self.retention.log_cb = cb

    # ------------------------------------------------------------------ #
    #  Жизненный цикл                                                     #
    # ------------------------------------------------------------------ #

    def _cam_dir(self, source_id):
        return os.path.join(self.archive_dir, f"cam{source_id}")

    def start(self):
        if self._started:
            return
        if not self.settings.enabled:
            self.log_cb("Архив: запись отключена в настройках")
            return
        if not has_ffmpeg():
            self.log_cb("Архив: ffmpeg не найден — запись недоступна")
            return

        self._started = True
        for source in self.source_manager.get_all_sources():
            if getattr(source, "record", True) and can_record(source.source_path):
                self._start_recorder(source)

        self.indexer.start()
        self.retention.start()
        self.log_cb(f"Архив: запущена запись {len(self.recorders)} камер(ы)")

    def _start_recorder(self, source):
        sid = source.source_id
        if sid in self.recorders:
            return
        rec = SegmentRecorder(
            sid, source.name, source.source_path,
            self._cam_dir(sid), self.settings, log_cb=self.log_cb,
        )
        if rec.start():
            self.recorders[sid] = rec

    def stop(self):
        if not self._started:
            return
        self._started = False
        # сначала останавливаем индексатор/очистку
        self.indexer.stop()
        self.retention.stop()
        # затем плавно гасим рекордеры (финализируем последние сегменты)
        with self._lock:
            recs = list(self.recorders.values())
            self.recorders.clear()
        for rec in recs:
            rec.stop()
        # финальное сканирование, чтобы только что закрытые сегменты попали в БД
        try:
            self.indexer.scan_once()
        except Exception:
            pass
        self.log_cb("Архив: запись остановлена")

    # ------------------------------------------------------------------ #
    #  Управление камерами (горячее)                                      #
    # ------------------------------------------------------------------ #

    def add_camera(self, source_id):
        src = self.source_manager.get_source(source_id)
        if not src or not self._started:
            return
        if getattr(src, "record", True) and can_record(src.source_path):
            with self._lock:
                self._start_recorder(src)

    def remove_camera(self, source_id):
        with self._lock:
            rec = self.recorders.pop(source_id, None)
        if rec:
            rec.stop()

    def set_recording(self, source_id, enabled):
        """Включить/выключить запись камеры на лету."""
        self.source_manager.set_recording(source_id, enabled)
        if not self._started:
            return
        if enabled:
            self.add_camera(source_id)
        else:
            self.remove_camera(source_id)

    def is_recording(self, source_id) -> bool:
        rec = self.recorders.get(source_id)
        return rec is not None and rec.is_alive()

    def status(self) -> dict:
        """Снимок состояния записи по камерам (для UI/диагностики)."""
        out = {}
        for sid, rec in self.recorders.items():
            out[sid] = {"alive": rec.is_alive(), "gap": rec.gap_since}
        return out

    # ------------------------------------------------------------------ #
    #  Запросы к архиву (для таймлайна и плеера)                          #
    # ------------------------------------------------------------------ #

    def segments_in_range(self, source_id, t0, t1):
        return self.db.segments_in_range(source_id, t0, t1)

    def find_segment_at(self, source_id, t):
        return self.db.find_segment_at(source_id, t)

    def next_segment_after(self, source_id, t):
        return self.db.next_segment_after(source_id, t)

    def archive_bounds(self, source_id):
        return self.db.archive_bounds(source_id)

    def alerts_in_range(self, source_id, t0, t1):
        return self.db.alerts_in_range(source_id, t0, t1)

    def nearest_alert(self, source_id, t, direction):
        return self.db.nearest_alert(source_id, t, direction)
