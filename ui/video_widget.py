import cv2
from PyQt6.QtWidgets import QLabel, QInputDialog
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer


class VideoWidget(QLabel):
    zone_added = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.current_pixmap = None
        self.zones = []
        self.zone_names = []
        self.active_zones = []
        self.moving_objects = []
        self.drawing = False
        self.start_point = None
        self.end_point = None
        self.frame_width = 0
        self.frame_height = 0
        self.draw_rectangles = True

        self.loading = True
        self.loading_angle = 0
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
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        self.frame_width, self.frame_height = w, h
        bytes_per_line = ch * w
        image = QImage(rgb.tobytes(), w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        self.current_pixmap = QPixmap.fromImage(image)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.loading:
            painter.fillRect(self.rect(), QColor(240, 240, 240))
            center = self.rect().center()
            r = 30
            painter.setPen(QPen(QColor(66, 133, 244), 4))
            painter.drawArc(center.x() - r, center.y() - r - 30, r * 2, r * 2, self.loading_angle * 16, 120 * 16)
            painter.setFont(QFont("Arial", 12))
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(center.x() - 150, center.y() + 30, 300, 30, Qt.AlignmentFlag.AlignCenter, "Соединение...")
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
                painter.setPen(QPen(QColor(255, 0, 0), 3))
                painter.setBrush(QColor(255, 0, 0, 25))
            else:
                painter.setPen(QPen(QColor(0, 165, 255), 2, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(0, 165, 255, 25))
            painter.drawRect(rect)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            name = self.zone_names[i] if i < len(self.zone_names) else f"Зона {i}"
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            painter.drawText(rect.x() + 4, rect.y() + 14, name)

        if self.drawing and self.start_point and self.end_point:
            painter.setPen(QPen(QColor(255, 255, 0), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(255, 255, 0, 25))
            painter.drawRect(QRect(self.start_point, self.end_point))
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
            if rect.width() >= 20 and rect.height() >= 20:
                name, ok = QInputDialog.getText(self, "Добавление зоны", "Введите название зоны", text=f"Зона {len(self.zones)}")
                name = name if ok and name else f"Зона {len(self.zones)}"
                self.zones.append((rect.x(), rect.y(), rect.width(), rect.height()))
                self.zone_names.append(name)
                self.zone_added.emit(self.zones)
            self.update()

    def mouseDoubleClickEvent(self, event):
        for i, zone in enumerate(self.zones):
            if QRect(*zone).contains(event.pos()):
                new_name, ok = QInputDialog.getText(self, "Редактирование зоны", f"Название для зоны {i}:", text=self.zone_names[i])
                if ok and new_name:
                    self.zone_names[i] = new_name
                    self.zone_added.emit(self.zones)
                    self.update()
                break

    def set_zones(self, zones, zone_names=None):
        self.zones = zones.copy()
        self.zone_names = zone_names.copy() if zone_names else [f"Зона {i}" for i in range(len(zones))]
        self.update()