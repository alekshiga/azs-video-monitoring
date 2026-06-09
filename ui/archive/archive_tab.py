"""
ArchiveTab — вкладка «Архив»: просмотр записанного видео с таймлайном,
перемоткой, скоростью, переходом по тревогам и экспортом клипа.
"""

import os
import subprocess
import threading
from datetime import datetime

import cv2
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFileDialog, QMessageBox, QInputDialog, QSizePolicy
)

from core.archive.ffmpeg_locator import ffmpeg_exe
from .timeline_widget import TimelineWidget
from .playback_engine import PlaybackThread

SPEEDS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]


class ArchiveTab(QWidget):
    _export_done = pyqtSignal(bool, str)

    def __init__(self, archive_manager, source_manager, db, parent=None):
        super().__init__(parent)
        self.archive = archive_manager
        self.source_manager = source_manager
        self.db = db
        self.current_source_id = None

        self.player = PlaybackThread(self)
        self.player.frame_ready.connect(self._on_frame)
        self.player.position.connect(self._on_position)
        self.player.segment_finished.connect(self._on_segment_finished)
        self.player.state_changed.connect(self._on_state_changed)
        self.player.start()

        self._setup_ui()
        self._export_done.connect(self._on_export_done)

        # троттлинг перезагрузки сегментов при панораме/зуме таймлайна
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(150)
        self._reload_timer.timeout.connect(self._reload_timeline_data)

        # периодическое обновление статуса записи
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(3000)
        self._status_timer.timeout.connect(self._refresh_rec_status)
        self._status_timer.start()

        self.refresh_cameras()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # верхняя панель
        top = QHBoxLayout()
        top.addWidget(QLabel("Камера:"))
        self.cam_combo = QComboBox()
        self.cam_combo.setMinimumWidth(180)
        self.cam_combo.currentIndexChanged.connect(self._on_camera_changed)
        top.addWidget(self.cam_combo)

        self.latest_btn = QPushButton("К последней записи")
        self.latest_btn.clicked.connect(self.seek_latest)
        top.addWidget(self.latest_btn)

        self.rec_status = QLabel("●")
        self.rec_status.setStyleSheet("color:#888;")
        top.addWidget(self.rec_status)
        top.addStretch()
        self.rec_toggle_btn = QPushButton("Запись: —")
        self.rec_toggle_btn.clicked.connect(self._toggle_recording)
        top.addWidget(self.rec_toggle_btn)
        root.addLayout(top)

        # видеоканва
        self.canvas = QLabel("Нет записи")
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setMinimumHeight(360)
        self.canvas.setStyleSheet("background:#222; color:#888;")
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.canvas, stretch=1)

        # транспорт
        tr = QHBoxLayout()
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(44)
        self.play_btn.clicked.connect(self._toggle_play)
        tr.addWidget(self.play_btn)

        self.step_back_btn = QPushButton("⏮ кадр")
        self.step_fwd_btn = QPushButton("кадр ⏭")
        self.step_back_btn.clicked.connect(lambda: self._step(-1))
        self.step_fwd_btn.clicked.connect(lambda: self._step(1))
        tr.addWidget(self.step_back_btn)
        tr.addWidget(self.step_fwd_btn)

        tr.addWidget(QLabel("Скорость:"))
        self.speed_combo = QComboBox()
        for s in SPEEDS:
            self.speed_combo.addItem(f"{s}×", s)
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        tr.addWidget(self.speed_combo)

        self.prev_evt_btn = QPushButton("◀ тревога")
        self.next_evt_btn = QPushButton("тревога ▶")
        self.prev_evt_btn.clicked.connect(lambda: self._jump_event(-1))
        self.next_evt_btn.clicked.connect(lambda: self._jump_event(1))
        tr.addWidget(self.prev_evt_btn)
        tr.addWidget(self.next_evt_btn)

        tr.addStretch()
        self.time_label = QLabel("—")
        self.time_label.setStyleSheet("font-family:monospace; font-size:12px;")
        tr.addWidget(self.time_label)
        root.addLayout(tr)

        ex = QHBoxLayout()
        self.export_btn = QPushButton("Экспорт клипа")
        self.export_btn.clicked.connect(self._export_clip)
        self.export_hint = QLabel("Встаньте на нужный момент и нажмите «Экспорт клипа»")
        self.export_hint.setStyleSheet("color:#666; font-size:11px;")
        ex.addWidget(self.export_btn)
        ex.addWidget(self.export_hint)
        ex.addStretch()
        root.addLayout(ex)

        self.timeline = TimelineWidget()
        self.timeline.seek_requested.connect(self._on_timeline_seek)
        self.timeline.range_changed.connect(lambda *_: self._reload_timer.start())
        root.addWidget(self.timeline)

    # ------------------------------------------------------------------ #
    #  Камеры                                                             #
    # ------------------------------------------------------------------ #

    def refresh_cameras(self):
        prev = self.current_source_id
        self.cam_combo.blockSignals(True)
        self.cam_combo.clear()
        for src in self.source_manager.get_sources_list():
            self.cam_combo.addItem(src["name"], src["id"])
        self.cam_combo.blockSignals(False)
        if self.cam_combo.count():
            idx = 0
            if prev is not None:
                found = self.cam_combo.findData(prev)
                if found >= 0:
                    idx = found
            self.cam_combo.setCurrentIndex(idx)
            self._on_camera_changed(idx)

    def _on_camera_changed(self, index):
        sid = self.cam_combo.itemData(index)
        if sid is None:
            return
        self.current_source_id = sid
        self.seek_latest()
        self._refresh_rec_status()

    def seek_latest(self):
        sid = self.current_source_id
        if sid is None:
            return
        bounds = self.archive.archive_bounds(sid)
        now = datetime.now().timestamp()
        if bounds:
            t0, t1 = bounds
            view_t1 = t1
            view_t0 = max(t0, t1 - 3600)
            self.timeline.set_view(view_t0, view_t1)
            self._reload_timeline_data()
            self.seek_to(sid, max(t0, t1 - 2))
        else:
            self.timeline.set_view(now - 3600, now)
            self._reload_timeline_data()
            self.canvas.setText("Записей пока нет")

    # ------------------------------------------------------------------ #
    #  Таймлайн данные                                                    #
    # ------------------------------------------------------------------ #

    def _reload_timeline_data(self):
        sid = self.current_source_id
        if sid is None:
            return
        t0, t1 = self.timeline.view_range()
        # с запасом по краям, чтобы при панораме данные уже были
        pad = (t1 - t0) * 0.5
        segs = self.archive.segments_in_range(sid, t0 - pad, t1 + pad)
        alerts = self.archive.alerts_in_range(sid, t0 - pad, t1 + pad)
        self.timeline.set_segments(segs)
        self.timeline.set_alerts(alerts)

    # ------------------------------------------------------------------ #
    #  Перемотка / воспроизведение                                        #
    # ------------------------------------------------------------------ #

    def seek_to(self, source_id, epoch_ts):
        """Публичный метод: перейти к моменту epoch_ts на камере source_id."""
        if source_id != self.current_source_id:
            idx = self.cam_combo.findData(source_id)
            if idx >= 0:
                self.cam_combo.setCurrentIndex(idx)  # вызовет _on_camera_changed
        self.current_source_id = source_id

        seg = self.archive.find_segment_at(source_id, epoch_ts)
        if not seg:
            seg = self.archive.next_segment_after(source_id, epoch_ts)
            if seg:
                epoch_ts = seg["start_ts"]
        if not seg:
            self.canvas.setText("Нет записи на этот момент")
            return
        offset_ms = max(0.0, (epoch_ts - seg["start_ts"]) * 1000.0)
        self.player.open_at(seg, offset_ms, autoplay=True)
        self.timeline.set_playhead(epoch_ts)

    def _on_timeline_seek(self, ts):
        if self.current_source_id is not None:
            self.seek_to(self.current_source_id, ts)

    def _on_segment_finished(self, end_ts):
        sid = self.current_source_id
        if sid is None:
            return
        nxt = self.archive.find_segment_at(sid, end_ts + 0.05) \
            or self.archive.next_segment_after(sid, end_ts)
        if nxt and self.player.is_playing():
            # бесшовно продолжаем, если следующий сегмент примыкает
            gap = nxt["start_ts"] - end_ts
            offset = 0.0
            self.player.open_at(nxt, offset, autoplay=True)
        else:
            self.player.pause()

    def _toggle_play(self):
        self.player.toggle()

    def _on_state_changed(self, playing):
        self.play_btn.setText("⏸" if playing else "▶")

    def _step(self, direction):
        if direction < 0:
            # шаг назад: перепрыгнуть на ~2 кадра раньше текущей позиции
            cur = getattr(self, "_last_epoch", None)
            if cur is not None:
                self.seek_to(self.current_source_id, cur - 0.08)
                self.player.pause()
        else:
            self.player.step(1)

    def _on_speed_changed(self, index):
        self.player.set_speed(self.speed_combo.itemData(index))

    def _jump_event(self, direction):
        sid = self.current_source_id
        if sid is None:
            return
        ref = getattr(self, "_last_epoch", None) or self.timeline.view_range()[1]
        a = self.archive.nearest_alert(sid, ref, direction)
        if a and a.get("ts") is not None:
            self.seek_to(sid, a["ts"])
        else:
            QMessageBox.information(self, "Архив", "Больше тревог в этом направлении нет.")

    # ------------------------------------------------------------------ #
    #  Кадры                                                              #
    # ------------------------------------------------------------------ #

    def _on_frame(self, frame, epoch):
        self._last_epoch = epoch
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(img)
            self.canvas.setPixmap(pix.scaled(
                self.canvas.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        except Exception:
            pass

    def _on_position(self, epoch):
        self._last_epoch = epoch
        self.timeline.set_playhead(epoch)
        self.time_label.setText(datetime.fromtimestamp(epoch).strftime("%d.%m.%Y  %H:%M:%S"))

    # ------------------------------------------------------------------ #
    #  Статус записи                                                      #
    # ------------------------------------------------------------------ #

    def _refresh_rec_status(self):
        sid = self.current_source_id
        if sid is None:
            return
        on = self.archive.is_recording(sid)
        self.rec_status.setStyleSheet("color:#d33;" if on else "color:#888;")
        self.rec_status.setToolTip("Идёт запись" if on else "Запись не ведётся")
        self.rec_toggle_btn.setText("Запись: вкл" if on else "Запись: выкл")

    def _toggle_recording(self):
        sid = self.current_source_id
        if sid is None:
            return
        on = self.archive.is_recording(sid)
        self.archive.set_recording(sid, not on)
        QTimer.singleShot(500, self._refresh_rec_status)

    def _export_clip(self):
        sid = self.current_source_id
        if sid is None:
            return
        cur = getattr(self, "_last_epoch", None)
        if cur is None:
            QMessageBox.information(self, "Экспорт",
                                    "Сначала станьте на нужный момент: кликните по таймлайну "
                                    "или запустите воспроизведение.")
            return
        dur, ok = QInputDialog.getInt(self, "Экспорт клипа",
                                      "Длительность клипа от текущего момента (сек):", 30, 1, 3600)
        if not ok:
            return
        t0, t1 = cur, cur + dur

        if ffmpeg_exe() is None:
            QMessageBox.warning(self, "Экспорт", "ffmpeg недоступен.")
            return

        segs = self.archive.segments_in_range(sid, t0, t1)
        if not segs:
            QMessageBox.information(self, "Экспорт", "Нет записи в выбранном интервале.")
            return

        default = f"clip_cam{sid}_{datetime.fromtimestamp(t0).strftime('%Y%m%d_%H%M%S')}.mp4"
        out_path, _ = QFileDialog.getSaveFileName(self, "Сохранить клип", default, "MP4 (*.mp4)")
        if not out_path:
            return

        self.export_btn.setEnabled(False)
        self.export_btn.setText("Экспорт…")
        threading.Thread(target=self._run_export, args=(segs, t0, t1, out_path),
                         daemon=True).start()

    def _run_export(self, segs, t0, t1, out_path):
        try:
            ff = ffmpeg_exe()
            first = segs[0]
            offset = max(0.0, t0 - first["start_ts"])
            duration = t1 - t0

            if len(segs) == 1:
                cmd = [ff, "-hide_banner", "-loglevel", "error",
                       "-ss", f"{offset:.3f}", "-i", first["path"],
                       "-t", f"{duration:.3f}", "-c", "copy",
                       "-y", out_path]
            else:
                # склейка нескольких сегментов через concat-демуксер
                list_path = out_path + ".concat.txt"
                with open(list_path, "w", encoding="utf-8") as f:
                    for s in segs:
                        p = s["path"].replace("\\", "/").replace("'", r"'\''")
                        f.write(f"file '{p}'\n")
                cmd = [ff, "-hide_banner", "-loglevel", "error",
                       "-f", "concat", "-safe", "0", "-i", list_path,
                       "-ss", f"{offset:.3f}", "-t", f"{duration:.3f}",
                       "-c", "copy", "-y", out_path]

            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if len(segs) > 1:
                try:
                    os.remove(out_path + ".concat.txt")
                except OSError:
                    pass
            ok = r.returncode == 0 and os.path.exists(out_path)
            msg = out_path if ok else r.stderr.decode("utf-8", "replace")[:300]
            self._export_done.emit(ok, msg)
        except Exception as e:
            self._export_done.emit(False, str(e))

    def _on_export_done(self, ok, msg):
        self.export_btn.setEnabled(True)
        self.export_btn.setText("Экспорт клипа")
        if ok:
            QMessageBox.information(self, "Экспорт", f"Клип сохранён:\n{msg}")
        else:
            QMessageBox.warning(self, "Экспорт", f"Не удалось создать клип:\n{msg}")

    # ------------------------------------------------------------------ #

    def shutdown(self):
        self.player.stop_playback()
