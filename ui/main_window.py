from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QTextEdit, QLabel, QFileDialog,
    QGroupBox, QScrollArea, QCheckBox, QComboBox
)

from input.source_manager import SourceManager
from input.video_thread import VideoThread
from ui.video_widget import VideoWidget


class MainWindow(QMainWindow):
    """
    Главное окно программы
    """
    def __init__(self, video_thread: VideoThread, source_manager: SourceManager):
        super().__init__()
        self.video_thread = video_thread
        self.source_manager = source_manager

        self.video_widget = None
        self.load_zones_btn = None
        self.save_zones_btn = None
        self.clear_zones_btn = None
        self.zones_count_label = None
        self.log_widget = None
        self.clear_log_btn = None
        self.source_combo = None

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
        control_group = QGroupBox("Выбор камеры")
        control_layout = QHBoxLayout()

        self.source_combo = QComboBox()
        self.refresh_btn = QPushButton("Обновить")
        control_layout.addWidget(self.source_combo)
        control_layout.addWidget(self.refresh_btn)

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
            status = "Успешно" if src['connected'] else "Ошибка"
            self.source_combo.addItem(f"{status} {src['name']}", src['id'])

        if sources:
            self.source_combo.setCurrentIndex(0)
            self._on_source_changed(0)
            self._add_log(f"Доступно источников: {len(sources)}")
        else:
            self._add_log("Нет доступных источников")

    def _on_source_changed(self, index):
        """Смена источника"""
        source_id = self.source_combo.itemData(index)
        if source_id:
            self.source_manager.set_active_source(source_id)
            self._add_log(f"Переключено на камеру {source_id}")

    def _load_zones(self):
        """
        Загрузка зон из файла
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл зон", "", "JSON Files (*.json)"
        )
        if filepath:
            # todo: загрузка зон из файла будет позже
            self._add_log(f"Загружены зоны из {filepath}")

    def _save_zones(self):
        """
        Сохранение зон в файл
        """
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Сохранить зоны", "zones.json", "JSON Files (*.json)"
        )
        if filepath:
            # todo: сохранение зон добавить позже
            self._add_log(f"Зоны сохранены в {filepath}")

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

    def closeEvent(self, event):
        self.video_thread.stop()
        event.accept()
