import cv2
from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt6.QtCore import Qt, QRect, pyqtSignal


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

        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: #1a1a2e; border:1px solid #16213e;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_frame(self, frame, active_zones = None, moving_objects = None):
        self.active_zones = active_zones or []
        self.moving_objects = moving_objects or []

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape

        self.frame_width = w
        self.frame_height = h

        bytes_per_line = ch * w
        image = QImage(
            rgb.data, w, h, bytes_per_line,
            QImage.Format.Format_RGB888
        ).copy()

        self.current_pixmap = QPixmap.fromImage(image)
        self.update()

    def paintEvent(self, event):
        painter = QPainter()

        if self.current_pixmap:
            painter.drawPixmap(self.rect(), self.current_pixmap)

        # Отрисовываем зоны (если есть)
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

