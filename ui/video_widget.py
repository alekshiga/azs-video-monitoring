import cv2
from PyQt6.QtWidgets import QLabel, QInputDialog, QMenu
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer


class VideoWidget(QLabel):
    zone_added = pyqtSignal(list)
    zone_double_clicked = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.current_pixmap = None
        self.zones = []
        self.display_zones = []
        self.zone_names = []
        self.active_zones = []
        self.moving_objects = []
        self.drawing = False
        self.start_point = None
        self.end_point = None
        self.frame_width = 0
        self.frame_height = 0
        self.draw_rectangles = True
        self.zone_rules = {}

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
        self._recalc_display_zones()
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

        for i, zone in enumerate(self.display_zones):
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
        if event.button() == Qt.MouseButton.RightButton:
            self._show_zone_context_menu(event.pos())
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.start_point = event.pos()
            self.end_point = event.pos()

    def _show_zone_context_menu(self, pos):
        zone_index = None
        for i, zone in enumerate(self.display_zones):
            if QRect(*zone).contains(pos):
                zone_index = i
                break

        if zone_index is None:
            return

        zone_name = self.zone_names[zone_index] if zone_index < len(self.zone_names) else f"Зона {zone_index}"
        menu = QMenu(self)
        delete_action = menu.addAction(f"🗑 Удалить «{zone_name}»")
        action = menu.exec(self.mapToGlobal(pos))
        if action == delete_action:
            self._delete_zone(zone_index)

    def _delete_zone(self, zone_index):
        self.zones.pop(zone_index)
        self.zone_names.pop(zone_index)
        if zone_index in self.zone_rules:
            del self.zone_rules[zone_index]
        # Переиндексируем правила зон с большим индексом
        new_rules = {}
        for idx, rules in self.zone_rules.items():
            new_idx = idx - 1 if idx > zone_index else idx
            new_rules[new_idx] = rules
        self.zone_rules = new_rules
        self._recalc_display_zones()
        self.zone_added.emit(self.zones)
        self.update()

    def mouseMoveEvent(self, event):
        if self.drawing:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            rect = QRect(self.start_point, self.end_point).normalized()
            if rect.width() >= 10 and rect.height() >= 10:
                name, ok = QInputDialog.getText(
                    self,
                    "Название зоны",
                    "Введите название зоны:",
                    text=f"Зона {len(self.zones)}"
                )
                zone_name = name if ok and name else f"Зона {len(self.zones)}"

                if self.frame_width > 0 and self.frame_height > 0:
                    widget_w = self.width()
                    widget_h = self.height()
                    scale_x = self.frame_width / widget_w
                    scale_y = self.frame_height / widget_h

                    x = int(rect.x() * scale_x)
                    y = int(rect.y() * scale_y)
                    w = int(rect.width() * scale_x)
                    h = int(rect.height() * scale_y)
                else:
                    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

                zone = (x, y, w, h)
                self.zones.append(zone)
                self.zone_names.append(zone_name)

                self._recalc_display_zones()
                self.zone_added.emit(self.zones)
                self.update()
            else:
                self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalc_display_zones()
        self.update()

    def _recalc_display_zones(self):
        """
        Пересчитывает зоны из координат кадра в координаты виджета
        """
        if self.frame_width == 0 or self.frame_height == 0:
            self.display_zones = self.zones.copy()
            return

        widget_w = self.width()
        widget_h = self.height()
        if widget_w == 0 or widget_h == 0:
            self.display_zones = self.zones.copy()
            return

        scale_x = widget_w / self.frame_width
        scale_y = widget_h / self.frame_height

        self.display_zones = []
        for (x, y, w, h) in self.zones:
            self.display_zones.append((
                int(x * scale_x),
                int(y * scale_y),
                int(w * scale_x),
                int(h * scale_y)
            ))

    def mouseDoubleClickEvent(self, event):
        for i, zone in enumerate(self.display_zones):
            if QRect(*zone).contains(event.pos()):
                self.zone_double_clicked.emit(i)
                break

    def set_zones(self, zones, zone_names=None, zone_rules=None):
        self.zones = zones.copy()
        self.zone_names = zone_names.copy() if zone_names else [f"Зона {i}" for i in range(len(zones))]
        if zone_rules:
            self.zone_rules = zone_rules.copy()
        else:
            self.zone_rules = {}
        self._recalc_display_zones()
        self.update()