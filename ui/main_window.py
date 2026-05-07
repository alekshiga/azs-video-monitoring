from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QTextEdit, QLabel, QFileDialog,
    QGroupBox, QScrollArea, QCheckBox
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
        self.start_btn = None
        self.stop_btn = None
        self.load_zones_btn = None
        self.save_zones_btn = None
        self.clear_zones_btn = None
        self.zones_count_label = None
        self.log_widget = None
        self.clear_log_btn = None

        self.setWindowTitle("Система мониторинга")
        self.setGeometry(100, 100, 1400, 800)
        self.setStyleSheet("""
                    QMainWindow { background-color: #1a1a2e; }
                    QPushButton {
                        padding: 6px 12px;
                        font-size: 12px;
                        border-radius: 4px;
                        border: none;
                    }
                    QPushButton:hover { background-color: #2a2a3e; }
                    QTextEdit {
                        background-color: #0f0f23;
                        color: #e0e0e0;
                        border: 1px solid #16213e;
                        border-radius: 4px;
                        font-family: monospace;
                        font-size: 11px;
                    }
                    QGroupBox {
                        color: #c0c0e0;
                        border: 1px solid #16213e;
                        border-radius: 4px;
                        margin-top: 8px;
                        padding-top: 12px;
                        font-weight: bold;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px;
                    }
                    QLabel { color: #c0c0e0; }
                    QCheckBox { color: #c0c0e0; }
                    QComboBox {
                        background-color: #0f0f23;
                        color: #e0e0e0;
                        border: 1px solid #16213e;
                        border-radius: 3px;
                        padding: 4px;
                    }
                    QSpinBox {
                        background-color: #0f0f23;
                        color: #e0e0e0;
                        border: 1px solid #16213e;
                        border-radius: 3px;
                        padding: 3px;
                    }
                    QTableWidget {
                        background-color: #0f0f23;
                        color: #e0e0e0;
                        border: 1px solid #16213e;
                        gridline-color: #16213e;
                    }
                    QHeaderView::section {
                        background-color: #0f0f23;
                        color: #c0c0e0;
                        padding: 4px;
                        border: 1px solid #16213e;
                    }
                """)
        self._setup_ui()
        self._connect_signals()

        sources = self.source_manager.get_all_sources()
        if sources:
            self.source_manager.set_active_source(sources[0].source_id)
            self._add_log(f"Активный источник: {sources[0].name}")
        else:
            self._add_log("Нет доступных источников видео")

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

        control_group = QGroupBox("Управление")
        control_layout = QHBoxLayout()

        self.start_btn = QPushButton("Старт")
        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.setEnabled(False)

        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_group.setLayout(control_layout)

        self.draw_rectangles_checkbox = QCheckBox("Отрисовка рамок")
        self.draw_rectangles_checkbox.setChecked(True)
        panel_layout.addWidget(self.draw_rectangles_checkbox)
        panel_layout.addWidget(control_group)

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
        buttons = [
            (self.start_btn, self._start_camera),
            (self.stop_btn, self._stop_camera),
            (self.load_zones_btn, self._load_zones),
            (self.save_zones_btn, self._save_zones),
            (self.clear_zones_btn, self._clear_zones),
            (self.clear_log_btn, self._clear_log),
        ]
        for btn, handler in buttons:
            btn.clicked.connect(handler)

        self.draw_rectangles_checkbox.stateChanged.connect(self._toggle_draw_rectangles)

        # Сигналы от VideoThread
        self.video_thread.frame_ready.connect(self._on_frame_ready)
        self.video_thread.log_signal.connect(self._add_log)

        # Сигналы от VideoWidget
        self.video_widget.zone_added.connect(self._on_zones_updated)

    def _start_camera(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._add_log("Запуск камеры")

    def _stop_camera(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._add_log("Остановка камеры")

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
