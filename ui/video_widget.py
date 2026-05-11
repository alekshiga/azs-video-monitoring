import cv2
import numpy as np
from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer


class VideoWidget(QLabel):
    zone_added = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        # Текущий кадр, зоны, имена зон, обнаруженные объекты
        self.current_pixmap = None
        self.zones = []
        self.zone_names = []
        self.active_zones = []
        self.moving_objects = []

        # Рисует ли сейчас пользователь зону (начальная и конечная точки)
        self.drawing = False
        self.start_point = None
        self.end_point = None

        self.frame_width = 0
        self.frame_height = 0

        self.draw_rectangles = True

        self.loading = True  # показываем загрузку, пока нет кадров
        self.loading_angle = 0  # угол для анимации
        self.loading_timer = QTimer()
        self.loading_timer.timeout.connect(self._rotate_loading)
        self.loading_timer.start(50)

        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: #f0f0f0; border:1px solid #cccccc;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_frame(self, frame, active_zones=None, moving_objects=None):
        self.loading = False
        self.loading_timer.stop()

        self.active_zones = active_zones or []
        self.moving_objects = moving_objects or []

        rgb = np.asarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        h, w, ch = rgb.shape

        self.frame_width = int(w)
        self.frame_height = int(h)

        bytes_per_line = int(ch * w)
        image = QImage(
            rgb.tobytes(), self.frame_width, self.frame_height,
            bytes_per_line, QImage.Format.Format_RGB888
        ).copy()

        self.current_pixmap = QPixmap.fromImage(image)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.loading:
            painter.fillRect(self.rect(), QColor(240, 240, 240))

            center = self.rect().center()
            radius = 30

            spinner_center_y = center.y() - 30
            pen = QPen(QColor(66, 133, 244), 4)
            painter.setPen(pen)
            start_angle = self.loading_angle * 16
            span_angle = 120 * 16
            painter.drawArc(center.x() - radius, spinner_center_y - radius,
                            radius * 2, radius * 2, start_angle, span_angle)

            font = QFont("Arial", 12, QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QColor(100, 100, 100))
            text_rect = QRect(center.x() - 150, spinner_center_y + 40, 300, 30)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "Соединение...")

            painter.end()
            return

        if self.current_pixmap:
            painter.drawPixmap(self.rect(), self.current_pixmap)

        if not self.draw_rectangles:
            painter.end()
            return

        for i, zone in enumerate(self.zones):
            rect = QRect(*zone)

            if i in self.active_zones:
                pen = QPen(QColor(255, 0, 0), 3)
                painter.setPen(pen)
                painter.setBrush(QColor(255, 0, 0, 25))
            else:
                pen = QPen(QColor(0, 165, 255), 2, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(QColor(0, 165, 255, 25))

            painter.drawRect(rect)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # подписываем название
            name = self.zone_names[i] if i < len(self.zone_names) else f"Зона {i}"
            font = QFont("Arial", 9, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(rect.x() + 4, rect.y() + 14, name)

        if self.drawing and self.start_point and self.end_point:
            pen = QPen(QColor(Qt.GlobalColor.yellow), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QColor(255, 255, 0, 25))
            rect = QRect(self.start_point, self.end_point)
            painter.drawRect(rect)

        painter.end()

    def _rotate_loading(self):
        if self.loading:
            self.loading_angle = (self.loading_angle + 30) % 360
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.start_point = event.pos()
            self.end_point = event.pos()

    def mouseMoveEvent(self, event):
        if self.drawing:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            rect = QRect(self.start_point, self.end_point).normalized()

            if rect.width() < 20 or rect.height() < 20:
                return

            zone = (rect.x(), rect.y(), rect.width(), rect.height())
            self.zones.append(zone)
            self.zone_names.append(f"Зона {len(self.zones) - 1}")
            print(f"Добавлена зона: {zone}")
            self.zone_added.emit(self.zones)
            self.update()

    def set_zones(self, zones, zone_names=None):
        """Установить зоны извне"""
        self.zones = zones.copy()
        if zone_names:
            self.zone_names = zone_names.copy()
        else:
            self.zone_names = [f"Зона {i}" for i in range(len(zones))]
            self.update()

