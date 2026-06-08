import os
import time
from datetime import datetime

from app_paths import user_data_path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QTextEdit, QLabel, QFileDialog,
    QGroupBox, QScrollArea, QCheckBox, QComboBox,
    QInputDialog, QMessageBox, QTabWidget
)

from output.pdf_report_exporter import export_log_to_pdf, export_stats_to_pdf
from output.incident_storage import save_snapshot

from core.zone_manager import ZoneManager
from input.source_manager import SourceManager
from input.video_thread import VideoThread
from output.email_notifier import EmailNotifier
from ui.image_stitching import ImageStitcher
from ui.video_widget import VideoWidget
from ui.rule_dialog import ZoneRulesDialog
from ui.alerts_widget import AlertsWidget
from ui.plates_widget import PlatesWidget


class MainWindow(QMainWindow):
    def __init__(self, video_thread: VideoThread, source_manager: SourceManager):
        super().__init__()
        self.video_thread = video_thread
        self.source_manager = source_manager
        self.email = EmailNotifier()

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
        self.anpr_checkbox = None

        self.current_mode = "single"
        self.current_source_id = None
        self._log_entries = []

        self.setWindowTitle("Система мониторинга")
        self.setGeometry(100, 100, 1600, 800)

        self._setup_ui()
        self._connect_signals()
        self._refresh_source_list()

        self.video_thread.alert_signal.connect(self.on_zone_alert)
        self.video_thread.all_frames_ready.connect(self._on_all_frames_ready)
        self.video_thread.camera_status_changed.connect(self._on_camera_status_changed)
        self.video_thread.stats_updated.connect(self._on_stats_updated)
        self.video_thread.start()
        self._add_log("Система мониторинга запущена")

        # Таймер обновления статистики — раз в 5 секунд, на случай если сигнал не дошёл
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(5000)
        self._stats_timer.timeout.connect(self._refresh_stats_label)
        self._stats_timer.timeout.connect(self._update_alerts_tab_title)
        self._stats_timer.start()

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
        # Корневой контейнер с вкладками: «Главная» и «Тревоги»
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        main_tab = QWidget()
        outer_layout = QVBoxLayout()
        outer_layout.setSpacing(5)
        main_tab.setLayout(outer_layout)

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

        self.anpr_checkbox = QCheckBox("Распознавание номеров (ANPR) на этой камере")
        panel_layout.addWidget(self.anpr_checkbox)

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

        stats_group = QGroupBox("Статистика за сеанс")
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel("Нет данных")
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet("font-size: 11px; color: #333;")
        stats_btn_row = QHBoxLayout()
        self.export_stats_btn = QPushButton("Экспорт PDF")
        self.reset_stats_btn = QPushButton("Сбросить")
        stats_btn_row.addWidget(self.export_stats_btn)
        stats_btn_row.addWidget(self.reset_stats_btn)
        stats_layout.addWidget(self.stats_label)
        stats_layout.addLayout(stats_btn_row)
        stats_group.setLayout(stats_layout)
        panel_layout.addWidget(stats_group)

        log_group = QGroupBox("Журнал событий")
        log_layout = QVBoxLayout()
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumHeight(250)
        log_layout.addWidget(self.log_widget)
        log_btn_layout = QHBoxLayout()
        self.export_pdf_btn = QPushButton("Экспорт PDF")
        self.clear_log_btn = QPushButton("Очистить")
        log_btn_layout.addWidget(self.export_pdf_btn)
        log_btn_layout.addWidget(self.clear_log_btn)

        log_layout.addLayout(log_btn_layout)
        log_group.setLayout(log_layout)
        panel_layout.addWidget(log_group)

        panel_layout.addStretch()
        panel_content.setLayout(panel_layout)
        scroll_area.setWidget(panel_content)
        top_layout.addWidget(scroll_area)
        outer_layout.addLayout(top_layout)

        # Вкладка «Главная»
        self.tabs.addTab(main_tab, "Главная")

        # Вкладка «Тревоги»
        self.alerts_widget = AlertsWidget(self.video_thread.db)
        self.alerts_widget.alerts_changed.connect(self._update_alerts_tab_title)
        self._alerts_tab_index = self.tabs.addTab(self.alerts_widget, "Тревоги")
        self._update_alerts_tab_title()

        # Вкладка "Автомобильные номера"
        self.plates_widget = PlatesWidget(self.video_thread.db)
        self.tabs.addTab(self.plates_widget, "Гос. номера")
        self.video_thread.plate_recognized.connect(self._on_plate_recognized)

    def _connect_signals(self):
        self.single_mode_btn.clicked.connect(self._set_single_mode)
        self.multi_mode_btn.clicked.connect(self._set_multi_mode)

        self.load_zones_btn.clicked.connect(self._load_zones)
        self.save_zones_btn.clicked.connect(self._save_zones)
        self.clear_zones_btn.clicked.connect(self._clear_zones)
        self.clear_log_btn.clicked.connect(self._clear_log)
        self.export_pdf_btn.clicked.connect(self._export_pdf)
        self.reset_stats_btn.clicked.connect(self._reset_stats)
        self.export_stats_btn.clicked.connect(self._export_stats_pdf)
        self.add_camera_btn.clicked.connect(self._add_network_camera)
        self.remove_btn.clicked.connect(self.remove_current_camera)

        self.draw_rectangles_checkbox.stateChanged.connect(self._toggle_draw_rectangles)
        self.anpr_checkbox.stateChanged.connect(self._toggle_anpr)

        self.video_thread.log_signal.connect(self._add_log)

        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.refresh_btn.clicked.connect(self._refresh_source_list)

        self.single_video_widget.zone_added.connect(self._on_zones_updated)
        self.single_video_widget.zone_double_clicked.connect(self.on_zone_double_clicked)

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
            indicator = "🟢" if src['connected'] else "🔴"
            self.source_combo.addItem(f"{indicator} {src['name']}", src['id'])
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
        self._sync_anpr_checkbox(source_id)

    def _sync_anpr_checkbox(self, source_id):
        src = self.source_manager.get_source(source_id)
        if src and self.anpr_checkbox:
            self.anpr_checkbox.blockSignals(True)
            self.anpr_checkbox.setChecked(bool(getattr(src, 'anpr', False)))
            self.anpr_checkbox.blockSignals(False)

    def _toggle_anpr(self, state):
        sid = self.current_source_id
        if not sid:
            return
        enabled = state == 2
        self.source_manager.set_anpr(sid, enabled)
        self._add_log(
            f"ANPR на камере {sid}: {'включено' if enabled else 'выключено'}"
        )

    def _load_zones_for_source(self, source_id):
        f = self.source_manager.get_zones_file(source_id)

        zm = self.video_thread.get_zone_manager(source_id) or ZoneManager()

        if f and zm.load_from_file(f):
            self.single_video_widget.set_zones(
                zm.zones, zm.zone_names, zm.zone_rules, zm.zone_types
            )
            self.video_thread.update_zones(
                zm.zones, source_id, zm.zone_names, zm.zone_rules, zm.zone_types
            )
            self._add_log(
                f"Загружено зон: {len(zm.zones)}, "
                f"правил: {sum(len(r) for r in zm.zone_rules.values())}"
            )
        else:
            self.single_video_widget.zones.clear()
            self.single_video_widget.zone_names.clear()
            self.single_video_widget.zone_rules.clear()
            self.single_video_widget.zone_types.clear()
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
        ZoneManager(camera_id=new_id).save_to_file(user_data_path("config", f"zones_cam_{new_id}.json"))
        if self.source_manager.connect_source(new_id):
            self._add_log(f"Добавлена камера: {name}")
        else:
            self._add_log(f"Камера добавлена, но не подключилась: {name}")
        self._refresh_source_list()

    def remove_current_camera(self):
        sid = self.source_combo.currentData()
        if not sid:
            return
        if QMessageBox.question(self, "Удаление источника", f"Удалить камеру '{self.source_combo.currentText()}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
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
            self.single_video_widget.set_zones(zm.zones, zm.zone_names, zm.zone_rules, zm.zone_types)
            self.video_thread.update_zones(zm.zones, sid, zm.zone_names, zm.zone_rules, zm.zone_types)
            self._update_zones_count()
            self._add_log(f"Загружены зоны из {path}")

    def _save_zones(self):
        if self.current_mode != "single":
            self._add_log("Переключитесь в режим одной камеры")
            return
        sid = self.current_source_id
        if not sid or not self.single_video_widget.zones:
            return
        zm = self.video_thread.get_zone_manager(sid)
        if zm:
            w = self.single_video_widget
            zm.set_zones(w.zones, w.zone_names, w.zone_rules, w.zone_types)
            zm.camera_id = sid
            zm.save_to_file(self.source_manager.get_zones_file(sid))
            self._add_log("Зоны и правила сохранены")

    def _clear_zones(self):
        if self.current_mode != "single":
            self._add_log("Переключитесь в режим 'Одна камера'")
            return
        sid = self.current_source_id
        if sid:
            self.single_video_widget.zones.clear()
            self.single_video_widget.zone_names.clear()
            self.single_video_widget.zone_rules.clear()
            self.single_video_widget.update()
            if zm := self.video_thread.get_zone_manager(sid):
                zm.clear_zones()
            self.video_thread.update_zones([], sid)
            self._update_zones_count()
            self._add_log("Зоны очищены")

    def _on_zones_updated(self, zones):
        if self.current_mode == "single" and self.current_source_id:
            sid = self.current_source_id
            w = self.single_video_widget
            if zm := self.video_thread.get_zone_manager(sid):
                zm.set_zones(zones, w.zone_names, w.zone_rules, w.zone_types)
                zm.camera_id = sid
                zm.save_to_file(self.source_manager.get_zones_file(sid))
            self.video_thread.update_zones(zones, sid, w.zone_names, w.zone_rules, w.zone_types)
            self._update_zones_count()

    def _clear_log(self):
        self.log_widget.clear()
        self._log_entries.clear()

    def _export_pdf(self):
        if not self._log_entries:
            QMessageBox.information(self, "Экспорт", "Журнал пустой, нечего экспортировать.")
            return

        default_name = f"report_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчет", default_name, "PDF (*.pdf)"
        )
        if not path:
            return

        src = self.source_manager.get_source(self.current_source_id) if self.current_source_id else None
        camera_name = src.name if src else ""

        stats_lines = []
        if self.current_source_id:
            stats_lines = self.video_thread.stats_tracker.as_log_lines(self.current_source_id)

        ok = export_log_to_pdf(self._log_entries, path, camera_name=camera_name,
                               stats_lines=stats_lines)
        if ok:
            self._add_log(f"Отчет сохранен: {os.path.basename(path)}")
            QMessageBox.information(self, "Готово", f"Отчет сохранен:\n{path}")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать PDF. Проверьте консоль.")

    def _update_zones_count(self):
        self.zones_count_label.setText(f"Зон: {len(self.single_video_widget.zones)}")

    def _add_log(self, text):
        if not hasattr(self, '_last_log_time'):
            self._last_log_time = 0
        if time.time() - self._last_log_time < 0.05:
            return
        self._last_log_time = time.time()
        entry = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
        self._log_entries.append(entry)
        self.log_widget.append(entry)
        if sb := self.log_widget.verticalScrollBar():
            sb.setValue(sb.maximum())

    def _toggle_draw_rectangles(self, state):
        draw = state == 2
        self.video_thread.draw_rectangles = draw
        self.single_video_widget.draw_rectangles = draw
        for w in self.image_stitcher.video_widgets.values():
            w.draw_rectangles = draw
        self._add_log(f"Отрисовка рамок: {'включена' if draw else 'выключена'}")

    def on_zone_double_clicked(self, zone_index):
        source_id = self.current_source_id
        if not source_id:
            self._add_log("Сначала выберите камеру")
            return

        zone_manager = self.video_thread.get_zone_manager(source_id)
        if not zone_manager:
            self._add_log("Ошибка: менеджер зон не найден")
            return

        zone_name = (
            zone_manager.zone_names[zone_index]
            if zone_index < len(zone_manager.zone_names)
            else f"Зона {zone_index}"
        )
        existing_rules = zone_manager.get_rules_for_zone(zone_index)

        dialog = ZoneRulesDialog(self, zone_name=zone_name, rules=existing_rules)
        dialog.exec()

        updated_rules = dialog.get_rules()
        if updated_rules:
            zone_manager.zone_rules[zone_index] = updated_rules
        else:
            zone_manager.zone_rules.pop(zone_index, None)

        self.single_video_widget.zone_rules = zone_manager.zone_rules
        self.single_video_widget.update()

        zones_file = self.source_manager.get_zones_file(source_id)
        if zones_file:
            zone_manager.save_to_file(zones_file)

        self._add_log(f"Правила зоны '{zone_name}': {len(updated_rules)} шт.")

    def on_zone_alert(self, zone_index, frame, source_id, class_name, time_in_zone):
        zone_name = None
        if source_id == self.current_source_id and 0 <= zone_index < len(self.single_video_widget.zone_names):
            zone_name = self.single_video_widget.zone_names[zone_index]
        elif source_id in self.image_stitcher.video_widgets:
            w = self.image_stitcher.video_widgets[source_id]
            if 0 <= zone_index < len(w.zone_names):
                zone_name = w.zone_names[zone_index]

        src = self.source_manager.get_source(source_id)

        if zone_name:
            clean_zone = ''.join(c if ord(c) < 128 else '' for c in zone_name)
            if not clean_zone.strip():
                clean_zone = f"Zone_{zone_index}"
        else:
            clean_zone = f"Zone_{zone_index}"

        if src:
            clean_source = ''.join(c if ord(c) < 128 else '' for c in src.name)
        else:
            clean_source = f"Camera_{source_id}"

        if class_name:
            clean_class = ''.join(c if ord(c) < 128 else '' for c in class_name)
            if not clean_class.strip():
                clean_class = "object"
        else:
            clean_class = "object"

        full_name = f"{clean_source} - {clean_zone}"
        self.email.send_alert(full_name, clean_class, time_in_zone, frame)

        # Жизненный цикл тревоги
        snapshot_path = save_snapshot(frame, source_id, zone_index)
        display_zone = zone_name or f"Зона {zone_index}"
        camera_disp = src.name if src else f"Камера {source_id}"
        self.video_thread.db.insert_alert(
            source_id=source_id,
            camera_name=camera_disp,
            zone_index=zone_index,
            zone_name=display_zone,
            class_name=class_name,
            message=class_name,
            time_in_zone=time_in_zone,
            snapshot=snapshot_path,
        )
        self._add_log(f"ТРЕВОГА: {camera_disp} / {display_zone} — {class_name}")
        self.alerts_widget.refresh()

    def _update_alerts_tab_title(self):
        if not hasattr(self, "_alerts_tab_index"):
            return
        new = self.alerts_widget.new_count()
        title = f"Тревоги ({new})" if new else "Тревоги"
        self.tabs.setTabText(self._alerts_tab_index, title)

    def _on_plate_recognized(self, source_id, plate, confidence):
        self._add_log(f"Распознан номер: {plate} ({confidence:.0%})")
        if hasattr(self, "plates_widget"):
            self.plates_widget.refresh()

    def _on_stats_updated(self, source_id=None):
        self._refresh_stats_label()

    def _refresh_stats_label(self):
        sid = self.current_source_id
        if not sid:
            return
        tracker = self.video_thread.stats_tracker
        all_stats = tracker.get_all_stats(sid)
        fmt = tracker.format_duration
        labels = {"car": "Легковые", "truck": "Грузовые", "bus": "Автобусы", "motorcycle": "Мото"}

        lines = []
        for zs in sorted(all_stats, key=lambda s: s.zone_index):
            sm = zs.summary()
            if sm["total_vehicles"] == 0 and sm["entered"] == 0:
                continue
            lines.append(f"<b>{sm['zone_name']}</b>")
            lines.append(f"Въехало: {sm['entered']} &nbsp;|&nbsp; Выехало: {sm['exited']}")
            if sm["conversion"] is not None:
                pct = sm["conversion"] * 100
                color = "#2e7d32" if abs(pct - 100) < 1 else "#c0392b"
                lines.append(f"Конверсия: <span style='color:{color}'>{pct:.0f}%</span>")
            lines.append(f"Всего ТС: {sm['total_vehicles']}")
            if sm["avg"] is not None:
                lines.append(f"Среднее время: {fmt(sm['avg'])}")
                lines.append(f"Мин: {fmt(sm['min'])}  |  Макс: {fmt(sm['max'])}")
            for cls, cnt in sm["by_class"].items():
                lines.append(f"{labels.get(cls, cls)}: {cnt}")
            lines.append("")

        self.stats_label.setText(
            "<br>".join(lines).strip() if lines else "Нет завершённых визитов"
        )

    def _export_stats_pdf(self):
        sid = self.current_source_id
        tracker = self.video_thread.stats_tracker
        if not tracker.get_all_stats(sid):
            QMessageBox.information(self, "Экспорт", "Нет данных для экспорта.")
            return

        default_name = f"stats_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить статистику", default_name, "PDF (*.pdf)")
        if not path:
            return

        src = self.source_manager.get_source(sid) if sid else None
        camera_name = src.name if src else ""

        ok = export_stats_to_pdf(tracker, sid, path, camera_name=camera_name)
        if ok:
            self._add_log(f"Статистика сохранена: {os.path.basename(path)}")
            QMessageBox.information(self, "Готово", f"Статистика сохранена:\n{path}")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать PDF.")

    def _reset_stats(self):
        sid = self.current_source_id
        self.video_thread.stats_tracker.reset(sid)
        self.stats_label.setText("Нет данных")
        self._add_log("Статистика сброшена")

    def _on_camera_status_changed(self, source_id, is_connected):
        """Индикатор статуса источника"""
        for i in range(self.source_combo.count()):
            if self.source_combo.itemData(i) == source_id:
                src = self.source_manager.get_source(source_id)
                if src:
                    indicator = "🟢" if is_connected else "🔴"
                    self.source_combo.setItemText(i, f"{indicator} {src.name}")
                break

    def closeEvent(self, event):
        if self.current_source_id and self.single_video_widget.zones:
            if zm := self.video_thread.get_zone_manager(self.current_source_id):
                zm.set_zones(
                    self.single_video_widget.zones,
                    self.single_video_widget.zone_names,
                    self.single_video_widget.zone_rules,
                )
                zm.save_to_file(self.source_manager.get_zones_file(self.current_source_id))
        self.video_thread.stop()
        event.accept()