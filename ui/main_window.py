import sys
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QTextEdit, QLabel, QFileDialog,
    QGroupBox, QCheckBox, QMessageBox, QComboBox,
    QSpinBox, QScrollArea, QInputDialog,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from ui.video_widget import VideoWidget


class MainWindow(QMainWindow):
    """
    Главное окно программы
    """
    def __init__(self):
        super().__init__()
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
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMinimumWidth(300)
        scroll_area.setMaximumWidth(350)

        scroll_content = QWidget()
        right_panel = QVBoxLayout()
        right_panel.setSpacing(6)
        right_panel.setContentsMargins(3, 3, 3, 3)