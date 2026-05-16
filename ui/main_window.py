import os
import time
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QTextEdit, QLabel, QFileDialog,
    QGroupBox, QScrollArea, QCheckBox, QComboBox,
    QInputDialog, QMessageBox
)

from core.zone_manager import ZoneManager
from input.source_manager import SourceManager
from input.video_thread import VideoThread
from output.telegram_notifier import TelegramNotifier
from ui.image_stitching import ImageStitcher
from ui.video_widget import VideoWidget


class MainWindow(QMainWindow):
    def __init__(self, video_thread: VideoThread, source_manager: SourceManager):
        super().__init__()
        self.video_thread = video_thread
        self.source_manager = source_manager
        self.telegram = TelegramNotifier()

        self.image_stitcher = None
        self.single_video_widget = None
        self.load_zones_btn = None
        self.save_zones_btn = None
        self.clear_zones_btn = None
        self.zones_count_label = None
        self.log_widget = None
        self.clear_log_btn = None
        self.source_combo = None
        self.add_camera_btn = None
        self.remove_btn = None
        self.refresh_btn = None
        self.single_mode_btn = None
        self.multi_mode_btn = None
        self.draw_rectangles_checkbox = None

        self.current_mode = "single"
        self.current_source_id = None

        self.setWindowTitle("Система мониторинга")
        self.setGeometry(100, 100, 1600, 800)

        self._setup_ui()
        self._connect_signals()
        self._refresh_source_list()

        self.video_thread.alert_signal.connect(self.on_zone_alert)
        self.video_thread.all_frames_ready.connect(self._on_all_frames_ready)
        self.video_thread.start()
        self._add_log("Система мониторинга запущена")

        # noinspection PyShadowingNames,PyUnusedLocal
        def _apply_stylesheet(self):
            """Применение стилей к окну (светлая тема)"""
            self.setStyleSheet("""
                QMainWindow { background-color: #f0f0f0; }
    
                QPushButton {
                    padding: 6px 12px;
                    font-size: 12px;
                    border-radius: 4px;
                    border: 1px solid #cccccc;
                    background-color: #ffffff;
                    color: #333333;
                }
                QPushButton:hover { 
                    background-color: #e6e6e6; 
                    border-color: #aaaaaa;
                }
                QPushButton:disabled { 
                    background-color: #f5f5f5; 
                    color: #999999;
                    border-color: #dddddd;
                }
    
                QTextEdit {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    font-family: monospace;
                    font-size: 11px;
                }
    
                QGroupBox {
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    margin-top: 8px;
                    padding-top: 12px;
                    font-weight: bold;
                    background-color: #fafafa;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                    background-color: #f0f0f0;
                }
    
                QLabel { 
                    color: #333333; 
                }
    
                QCheckBox { 
                    color: #333333; 
                    spacing: 8px;
                }
    
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    background-color: #ffffff;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                }
    
                QCheckBox::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
            """)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout()
        outer_layout.setSpacing(5)
        central.setLayout(outer_layout)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self.video_container = QWidget()
        self.video_container_layout = QHBoxLayout()
        self.video_container_layout.setContentsMargins(0, 0, 0, 0)
        self.video_container.setLayout(self.video_container_layout)

        self.single_video_widget = VideoWidget()
        self.image_stitcher = ImageStitcher()

        self.video_container_layout.addWidget(self.single_video_widget)
        self.video_container_layout.addWidget(self.image_stitcher)
        self.image_stitcher.hide()

        top_layout.addWidget(self.video_container)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumWidth(320)
        scroll_area.setMaximumWidth(360)

        panel_content = QWidget()
        panel_layout = QVBoxLayout()
        panel_layout.setSpacing(6)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        mode_group = QGroupBox("Режим просмотра")
        mode_layout = QHBoxLayout()
        self.single_mode_btn = QPushButton("Одна камера")
        self.multi_mode_btn = QPushButton("Все камеры")
        self.single_mode_btn.setCheckable(True)
        self.multi_mode_btn.setCheckable(True)
        self.single_mode_btn.setChecked(True)
        mode_layout.addWidget(self.single_mode_btn)
        mode_layout.addWidget(self.multi_mode_btn)
        mode_group.setLayout(mode_layout)
        panel_layout.addWidget(mode_group)

        control_group = QGroupBox("Выбор камеры")
        control_layout = QVBoxLayout()
        select_layout = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(140)
        self.source_combo.setMaximumWidth(160)
        self.refresh_btn = QPushButton("Обновить")
        select_layout.addWidget(self.source_combo)
        select_layout.addWidget(self.refresh_btn)
        control_layout.addLayout(select_layout)

        edit_layout = QHBoxLayout()
        self.add_camera_btn = QPushButton("Добавить")
        self.remove_btn = QPushButton("Удалить")
        edit_layout.addWidget(self.add_camera_btn)
        edit_layout.addWidget(self.remove_btn)
        control_layout.addLayout(edit_layout)
        control_group.setLayout(control_layout)
        panel_layout.addWidget(control_group)

        self.draw_rectangles_checkbox = QCheckBox("Отрисовка рамок")
        self.draw_rectangles_checkbox.setChecked(True)
        panel_layout.addWidget(self.draw_rectangles_checkbox)

        zones_group = QGroupBox("Зоны контроля")
        zones_layout = QVBoxLayout()
        zones_btn_layout = QHBoxLayout()
        self.load_zones_btn = QPushButton("Загрузить")
        self.save_zones_btn = QPushButton("Сохранить")
        self.clear_zones_btn = QPushButton("Очистить")
        zones_btn_layout.addWidget(self.load_zones_btn)
        zones_btn_layout.addWidget(self.save_zones_btn)
        zones_btn_layout.addWidget(self.clear_zones_btn)
        self.zones_count_label = QLabel("Зон: 0")
        zones_layout.addLayout(zones_btn_layout)
        zones_layout.addWidget(self.zones_count_label)
        zones_group.setLayout(zones_layout)
        panel_layout.addWidget(zones_group)

        log_group = QGroupBox("Журнал событий")
        log_layout = QVBoxLayout()
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumHeight(250)
        self.clear_log_btn = QPushButton("Очистить")
        log_layout.addWidget(self.log_widget)
        log_layout.addWidget(self.clear_log_btn)
        log_group.setLayout(log_layout)
        panel_layout.addWidget(log_group)

        panel_layout.addStretch()
        panel_content.setLayout(panel_layout)
        scroll_area.setWidget(panel_content)
        top_layout.addWidget(scroll_area)
        outer_layout.addLayout(top_layout)

    def _connect_signals(self):
        self.single_mode_btn.clicked.connect(self._set_single_mode)
        self.multi_mode_btn.clicked.connect(self._set_multi_mode)

        self.load_zones_btn.clicked.connect(self._load_zones)
        self.save_zones_btn.clicked.connect(self._save_zones)
        self.clear_zones_btn.clicked.connect(self._clear_zones)
        self.clear_log_btn.clicked.connect(self._clear_log)
        self.add_camera_btn.clicked.connect(self._add_network_camera)
        self.remove_btn.clicked.connect(self.remove_current_camera)

        self.draw_rectangles_checkbox.stateChanged.connect(self._toggle_draw_rectangles)

        self.video_thread.log_signal.connect(self._add_log)

        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.refresh_btn.clicked.connect(self._refresh_source_list)

        self.single_video_widget.zone_added.connect(self._on_zones_updated)

    def _set_single_mode(self):
        self.current_mode = "single"
        self.single_mode_btn.setChecked(True)
        self.multi_mode_btn.setChecked(False)
        self.single_video_widget.show()
        self.image_stitcher.hide()
        if self.current_source_id:
            self._load_zones_for_source(self.current_source_id)
        self._add_log("Режим: одна камера")

    def _set_multi_mode(self):
        self.current_mode = "multi"
        self.single_mode_btn.setChecked(False)
        self.multi_mode_btn.setChecked(True)
        self.single_video_widget.hide()
        self.image_stitcher.show()
        self._add_log("Режим: все камеры")

    def _refresh_source_list(self):
        self.source_combo.clear()
        for src in self.source_manager.get_sources_list():
            self.source_combo.addItem(src['name'], src['id'])
        if self.source_combo.count() > 0:
            self.source_combo.setCurrentIndex(0)
            self._on_source_changed(0)

    def _on_source_changed(self, index):
        source_id = self.source_combo.itemData(index)
        if not source_id:
            return
        self.current_source_id = source_id
        self.source_manager.set_active_source(source_id)
        self._add_log(f"Выбрана камера {source_id}")
        self._load_zones_for_source(source_id)

    def _load_zones_for_source(self, source_id):
        zm = self.video_thread.get_zone_manager(source_id)
        if zm:
            f = self.source_manager.get_zones_file(source_id)
            if f and zm.load_from_file(f):
                self.single_video_widget.set_zones(zm.zones, zm.zone_names)
                self.video_thread.update_zones(zm.zones, source_id)
                self._add_log(f"Загружено зон: {len(zm.zones)}")
            else:
                self.single_video_widget.zones.clear()
                self.single_video_widget.zone_names.clear()
                self.video_thread.update_zones([], source_id)
        self._update_zones_count()

    def _add_network_camera(self):
        name, ok = QInputDialog.getText(self, "Добавить камеру", "Название:")
        if not ok or not name:
            return
        path, ok = QInputDialog.getText(self, "Путь", "RTSP или путь к видеофайлу:")
        if not ok or not path:
            return
        new_id = self.source_manager.add_ip_source(name, path)
        ZoneManager(camera_id=new_id).save_to_file(f"config/zones_cam_{new_id}.json")
        if self.source_manager.connect_source(new_id):
            self._add_log(f"Добавлена камера: {name}")
        else:
            self._add_log(f"Камера добавлена, но не подключилась: {name}")
        self._refresh_source_list()

    def remove_current_camera(self):
        sid = self.source_combo.currentData()
        if not sid:
            return
        if QMessageBox.question(self, "Удаление", f"Удалить камеру '{self.source_combo.currentText()}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.video_thread.remove_source(sid)
            f = self.source_manager.get_zones_file(sid)
            if f and os.path.exists(f):
                os.remove(f)
            self.source_manager.remove_source(sid)
            self._refresh_source_list()
            if self.source_combo.count() == 0:
                self.current_source_id = None
                self.single_video_widget.zones.clear()
                self.single_video_widget.zone_names.clear()
                self.single_video_widget.update()
            self._add_log(f"Удалена камера {sid}")

    def _on_all_frames_ready(self, all_frames):
        if self.current_mode == "multi":
            srcs = [{'id': f['id']} for f in all_frames if f['frame'] is not None]
            if srcs:
                self.image_stitcher.set_sources(srcs)
            for fd in all_frames:
                if fd['frame'] is not None:
                    self.image_stitcher.update_frame(fd['id'], fd['frame'], fd['active_zones'], fd['objects'])
        elif self.current_mode == "single" and self.current_source_id:
            for fd in all_frames:
                if fd['id'] == self.current_source_id and fd['frame'] is not None:
                    self.single_video_widget.set_frame(fd['frame'], fd['active_zones'], fd['objects'])
                    break

    def _load_zones(self):
        if self.current_mode != "single":
            self._add_log("Переключитесь в режим 'Одна камера'")
            return
        sid = self.current_source_id
        if not sid:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Загрузить зоны", f"zones_cam_{sid}.json", "JSON (*.json)")
        if not path:
            return
        zm = self.video_thread.get_zone_manager(sid)
        if zm and zm.load_from_file(path):
            self.single_video_widget.set_zones(zm.zones, zm.zone_names)
            self.video_thread.update_zones(zm.zones, sid)
            self._update_zones_count()
            self._add_log(f"Загружены зоны из {path}")

    def _save_zones(self):
        if self.current_mode != "single":
            self._add_log("Переключитесь в режим 'Одна камера'")
            return
        sid = self.current_source_id
        if not sid or not self.single_video_widget.zones:
            return
        zm = self.video_thread.get_zone_manager(sid)
        if zm:
            zm.set_zones(self.single_video_widget.zones, self.single_video_widget.zone_names)
            zm.camera_id = sid
            zm.save_to_file(self.source_manager.get_zones_file(sid))
            self._add_log("Зоны сохранены")

    def _clear_zones(self):
        if self.current_mode != "single":
            self._add_log("Переключитесь в режим 'Одна камера'")
            return
        sid = self.current_source_id
        if sid:
            self.single_video_widget.zones.clear()
            self.single_video_widget.zone_names.clear()
            self.single_video_widget.update()
            if zm := self.video_thread.get_zone_manager(sid):
                zm.clear_zones()
            self.video_thread.update_zones([], sid)
            self._update_zones_count()
            self._add_log("Зоны очищены")

    def _on_zones_updated(self, zones):
        if self.current_mode == "single" and self.current_source_id:
            self.video_thread.update_zones(zones, self.current_source_id)
            self._update_zones_count()

    def _clear_log(self):
        self.log_widget.clear()

    def _update_zones_count(self):
        self.zones_count_label.setText(f"Зон: {len(self.single_video_widget.zones)}")

    def _add_log(self, text):
        if not hasattr(self, '_last_log_time'):
            self._last_log_time = 0
        if time.time() - self._last_log_time < 0.05:
            return
        self._last_log_time = time.time()
        self.log_widget.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")
        if sb := self.log_widget.verticalScrollBar():
            sb.setValue(sb.maximum())

    def _toggle_draw_rectangles(self, state):
        draw = state == 2
        self.video_thread.draw_rectangles = draw
        self.single_video_widget.draw_rectangles = draw
        for w in self.image_stitcher.video_widgets.values():
            w.draw_rectangles = draw
        self._add_log(f"Отрисовка рамок: {'включена' if draw else 'выключена'}")

    def on_zone_alert(self, zone_index, frame, source_id):
        name = None
        if source_id == self.current_source_id and 0 <= zone_index < len(self.single_video_widget.zone_names):
            name = self.single_video_widget.zone_names[zone_index]
        elif source_id in self.image_stitcher.video_widgets:
            w = self.image_stitcher.video_widgets[source_id]
            if 0 <= zone_index < len(w.zone_names):
                name = w.zone_names[zone_index]
        src = self.source_manager.get_source(source_id)
        full = f"{src.name} - {name}" if src and name else f"{src.name} - зона {zone_index}" if src else f"Камера {source_id} - зона {zone_index}"
        self.telegram.send_alert(zone_index, full, frame)

    def closeEvent(self, event):
        if self.current_source_id and self.single_video_widget.zones:
            if zm := self.video_thread.get_zone_manager(self.current_source_id):
                zm.set_zones(self.single_video_widget.zones, self.single_video_widget.zone_names)
                zm.save_to_file(self.source_manager.get_zones_file(self.current_source_id))
        self.video_thread.stop()
        event.accept()