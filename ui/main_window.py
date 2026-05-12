import os
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
from ui.video_widget import VideoWidget
from output.telegram_notifier import TelegramNotifier


class MainWindow(QMainWindow):
    """
    Главное окно программы
    """
    def __init__(self, video_thread: VideoThread, source_manager: SourceManager):
        super().__init__()
        # Управление
        self.video_thread = video_thread # Видеопоток
        self.source_manager = source_manager # Источниками
        self.telegram = TelegramNotifier()  # Telegram

        self.video_widget = None
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

        self.setWindowTitle("Система мониторинга")
        self.setGeometry(100, 100, 1400, 800)

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

                QScrollArea {
                    border: none;
                    background-color: transparent;
                }

                QScrollBar:vertical {
                    background-color: #f0f0f0;
                    width: 10px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 5px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }

                QScrollBar:horizontal {
                    background-color: #f0f0f0;
                    height: 10px;
                    border-radius: 5px;
                }
                QScrollBar::handle:horizontal {
                    background-color: #c0c0c0;
                    border-radius: 5px;
                    min-width: 30px;
                }
                QScrollBar::handle:horizontal:hover {
                    background-color: #a0a0a0;
                }
            """)
        self._setup_ui()
        self._connect_signals()
        self._refresh_source_list()

        # Запускаем поток видео
        self.video_thread.start()
        self._add_log("Система мониторинга запущена")

    def _setup_ui(self):
        """
        Создание пользовательского интерфейса
        """
        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout()
        outer_layout.setSpacing(5)
        central.setLayout(outer_layout)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        # Видео
        self.video_widget = VideoWidget()
        top_layout.addWidget(self.video_widget)

        # Правая панель с прокруткой
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumWidth(280)
        scroll_area.setMaximumWidth(320)

        panel_content = QWidget()
        panel_layout = QVBoxLayout()
        panel_layout.setSpacing(6)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Группа: Выбор камеры
        control_group = QGroupBox("Управление камерами")
        control_layout = QVBoxLayout()

        select_layout = QHBoxLayout()
        self.source_combo = QComboBox()
        self.refresh_btn = QPushButton("Обновить")
        select_layout.addWidget(self.source_combo)
        select_layout.addWidget(self.refresh_btn)
        control_layout.addLayout(select_layout)

        edit_layout = QHBoxLayout()
        self.add_camera_btn = QPushButton("Добавить камеру")
        self.remove_btn = QPushButton("Удалить")
        edit_layout.addWidget(self.add_camera_btn)
        edit_layout.addWidget(self.remove_btn)
        control_layout.addLayout(edit_layout)

        control_group.setLayout(control_layout)
        panel_layout.addWidget(control_group)

        # Чекбокс отрисовки рамок
        self.draw_rectangles_checkbox = QCheckBox("Отрисовка рамок")
        self.draw_rectangles_checkbox.setChecked(True)
        panel_layout.addWidget(self.draw_rectangles_checkbox)

        # Группа: Зоны
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

        # Группа: Журнал
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
        """Подключение сигналов"""
        # Кнопки
        if self.load_zones_btn:
            self.load_zones_btn.clicked.connect(self._load_zones)
        if self.save_zones_btn:
            self.save_zones_btn.clicked.connect(self._save_zones)
        if self.clear_zones_btn:
            self.clear_zones_btn.clicked.connect(self._clear_zones)
        if self.clear_log_btn:
            self.clear_log_btn.clicked.connect(self._clear_log)
        if self.add_camera_btn:
            self.add_camera_btn.clicked.connect(self._add_network_camera)
        if self.remove_btn:
            self.remove_btn.clicked.connect(self.remove_current_camera)

        if self.draw_rectangles_checkbox:
            self.draw_rectangles_checkbox.stateChanged.connect(self._toggle_draw_rectangles)

        # Сигналы от VideoThread
        if self.video_thread:
            self.video_thread.frame_ready.connect(self._on_frame_ready)
            self.video_thread.log_signal.connect(self._add_log)

        # Сигналы от VideoWidget
        if self.video_widget:
            self.video_widget.zone_added.connect(self._on_zones_updated)

        # Сигнал при выборе источника + обновление источников
        if self.source_combo:
            self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        if self.refresh_btn:
            self.refresh_btn.clicked.connect(self._refresh_source_list)

    def _refresh_source_list(self):
        self.source_combo.clear()
        sources = self.source_manager.get_sources_list()
        for src in sources:
            self.source_combo.addItem(src['name'], src['id'])

        if sources:
            self.source_combo.setCurrentIndex(0)
            self._on_source_changed(0)
            self._add_log(f"Доступно источников: {len(sources)}")
        else:
            self._add_log("Нет доступных источников")

    def _on_source_changed(self, index):
        """Смена источника"""
        source_id = self.source_combo.itemData(index)
        if not source_id:
            return

        self.source_manager.set_active_source(source_id)
        self._add_log(f"Переключено на камеру {source_id}")

        # Автоматически подгружаем зоны для этой камеры
        zone_manager = self.video_thread.get_zone_manager(source_id)
        if zone_manager:
            zones_file = self.source_manager.get_zones_file(source_id)
            if zones_file and zone_manager.load_from_file(zones_file):
                self.video_widget.set_zones(zone_manager.zones, zone_manager.zone_names)
                self.video_thread.update_zones(zone_manager.zones, source_id)
                self._add_log(f"Загружено зон: {len(zone_manager.zones)}")
            else:
                self.video_widget.zones.clear()
                self.video_widget.zone_names.clear()
                self.video_widget.update()
                self.video_thread.update_zones([], source_id)
                self._add_log("Нет сохранённых зон для этой камеры")

        self._update_zones_count()

    def _add_network_camera(self):
        """Добавление источника"""
        name, ok = QInputDialog.getText(
            self,
            "Добавить камеру",
            "Введите название камеры: "
        )
        if not ok or not name:
            return

        rtsp_url, ok = QInputDialog.getText(
            self,
            "RTSP адрес",
            "Формат: rtsp://ip:порт/путь\n"
            "Пример: rtsp://192.168.1.100:554/stream1\n\n"
            "Если камера с авторизацией:\n"
            "rtsp://логин:пароль@ip:порт/путь"
        )

        if not ok or not rtsp_url:
            return

        if not rtsp_url.startswith("rtsp://"):
            QMessageBox.warning(self, "Ошибка", "RTSP адрес должен начинаться с rtsp://")
            return

        new_id = self.source_manager.add_ip_source(name, rtsp_url)

        zones_file = f"config/zones_cam_{new_id}.json"
        zone_manager = ZoneManager(camera_id=new_id)
        zone_manager.save_to_file(zones_file)

        if self.source_manager.connect_source(new_id):
            self._add_log(f"Добавлена камера: {name}")
            self._add_log(f"   RTSP: {rtsp_url[:50]}...")
        else:
            self._add_log(f"Камера добавлена, но соединение не установлено: {name}")
            self._add_log(f"   Проверьте RTSP адрес: {rtsp_url}")

        self._refresh_source_list()

        index = self.source_combo.findData(new_id)
        if index >= 0:
            self.source_combo.setCurrentIndex(index)

    def remove_current_camera(self):
        """Удаление текущей (отслеживаемой) камеры"""
        source_id = self.source_combo.currentData()
        if not source_id:
            self._add_log("Нет выбранной камеры")
            return

        camera_name = self.source_combo.currentText()

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить камеру '{camera_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:

            zones_file = self.source_manager.get_zones_file(source_id)
            if zones_file and os.path.exists(zones_file):
                os.remove(zones_file)
                self._add_log(f"Удалён файл зон камеры")

            self.source_manager.remove_source(source_id)
            self._refresh_source_list()
            self._add_log(f"Удалена камера: {camera_name}")

            if self.source_combo.count() == 0:
                self.source_manager.active_source_id = None
                self.video_widget.zones.clear()
                self.video_widget.zone_names.clear()
                self.video_widget.update()

    def _load_zones(self):
        """Загрузка зон из файла для ТЕКУЩЕЙ камеры"""
        source_id = self.source_combo.currentData()
        if not source_id:
            self._add_log("Сначала выберите камеру")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл зон", f"zones_cam_{source_id}.json", "JSON Files (*.json)"
        )
        if not filepath:
            return

        zone_manager = self.video_thread.get_zone_manager(source_id)
        if not zone_manager:
            self._add_log("Ошибка: менеджер зон не найден")
            return

        if zone_manager.load_from_file(filepath):
            self.video_widget.set_zones(zone_manager.zones, zone_manager.zone_names)
            self.video_thread.update_zones(zone_manager.zones, source_id)
            self._update_zones_count()
            self._add_log(f"Загружены зоны из {filepath}")
        else:
            self._add_log(f"Ошибка загрузки зон из {filepath}")

    def _save_zones(self):
        """Сохранение зон в файл"""
        source_id = self.source_combo.currentData()
        if not source_id:
            self._add_log("Сначала выберите камеру")
            return

        zones = self.video_widget.zones
        zone_names = self.video_widget.zone_names

        if not zones:
            self._add_log("Нет зон для сохранения")
            return

        # Получаем ZoneManager для текущей камеры
        zone_manager = self.video_thread.get_zone_manager(source_id)
        if not zone_manager:
            self._add_log("Ошибка: менеджер зон не найден")
            return

        # Обновляем зоны в менеджере
        zone_manager.set_zones(zones, zone_names)
        zone_manager.camera_id = source_id

        zones_file = self.source_manager.get_zones_file(source_id)
        if zone_manager.save_to_file(zones_file):
            self._add_log(f"Зоны сохранены (камера {source_id})")
        else:
            self._add_log(f"Ошибка сохранения зон")

    def _clear_zones(self):
        self.video_widget.zones.clear()
        self.video_widget.zone_names.clear()
        self.video_widget.update()
        self._update_zones_count()
        self._add_log("Зоны очищены")

    def _clear_log(self):
        self.log_widget.clear()

    def _on_frame_ready(self, frame, active_zones, moving_objects):
        """
        Приём кадра из видеопотока
        """
        self.video_widget.set_frame(frame, active_zones, moving_objects)

    def _on_zones_updated(self, zones):
        active_id = self.source_manager.active_source_id
        if active_id:
            self.video_thread.update_zones(zones, active_id)
        self._update_zones_count()

    def _update_zones_count(self):
        count = len(self.video_widget.zones)
        self.zones_count_label.setText(f"Зон: {count}")

    def _add_log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_widget.append(f"[{timestamp}] {text}")
        # Автопрокрутка вниз
        scrollbar = self.log_widget.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def _toggle_draw_rectangles(self, state):
        draw = state == 2  # Qt.Checked
        self.video_thread.draw_rectangles = draw
        self.video_widget.draw_rectangles = draw
        self._add_log(f"Отрисовка рамок: {'включена' if draw else 'выключена'}")

    def on_zone_alert(self, zone_index, frame, source_id):
        """
        Обработчик тревоги в зоне наблюдения
        :param zone_index: индекс зоны
        :param frame: кадр с нарушением
        :param source_id: идентификатор источника
        """
        zone_name = None
        if zone_index < len(self.video_widget.zone_names):
            zone_name = self.video_widget.zone_names[zone_index]
        source = self.source_manager.get_source(source_id)
        if source and zone_name:
            zone_name = f"{source.name} - {zone_name}"
        elif source:
            zone_name = f"{source.name} - зона {zone_index}"
        self.telegram.send_alert(zone_index, zone_name, frame)

    def closeEvent(self, event):
        source_id = self.source_combo.currentData()
        if source_id:
            zones = self.video_widget.zones
            if zones:
                zone_manager = self.video_thread.get_zone_manager(source_id)
                if zone_manager:
                    zone_manager.set_zones(zones, self.video_widget.zone_names)
                    zones_file = self.source_manager.get_zones_file(source_id)
                    zone_manager.save_to_file(zones_file)
                    self._add_log("Зоны сохранены")

        self.video_thread.stop()
        event.accept()
