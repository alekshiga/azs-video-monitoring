import cv2
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt6.QtWidgets import QLabel, QMenu, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QRadioButton, \
    QGroupBox, QLabel as QLabelWidget

ZONE_TYPE_CONTROL  = "control"   # зона с правилами и алертами
ZONE_TYPE_COUNTING = "counting"  # зона подсчёта клиентов

# Цвета для каждого типа зоны (обычный / активный)
ZONE_COLORS = {
    ZONE_TYPE_CONTROL:  {"normal": QColor(0, 165, 255),  "active": QColor(255, 0, 0)},
    ZONE_TYPE_COUNTING: {"normal": QColor(50, 200, 80),  "active": QColor(255, 165, 0)},
}


class ZoneCreateDialog(QDialog):
    """Диалог создания зоны: имя + тип (контроль или подсчет)"""
    def __init__(self, parent=None, default_name="", counting_disabled=False):
        super().__init__(parent)
        self.setWindowTitle("Новая зона")
        self.setFixedWidth(380)
        self.setStyleSheet("""
            QRadioButton {
                spacing: 8px;
                font-size: 12px;
                color: #333333;
                padding: 4px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #aaaaaa;
                background-color: #ffffff;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #27ae60;
                background-color: #27ae60;
            }
            QRadioButton::indicator:hover {
                border-color: #27ae60;
            }
            QRadioButton:disabled {
                color: #aaaaaa;
            }
            QRadioButton::indicator:disabled {
                border-color: #cccccc;
                background-color: #f0f0f0;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(QLabelWidget("Название зоны:"))
        self.name_edit = QLineEdit(default_name)
        layout.addWidget(self.name_edit)

        type_group = QGroupBox("Тип зоны")
        type_layout = QVBoxLayout(type_group)
        type_layout.setSpacing(6)
        self.rb_control  = QRadioButton("Зона контроля")
        self.rb_counting = QRadioButton("Зона подсчета ")
        self.rb_control.setChecked(True)
        if counting_disabled:
            self.rb_counting.setEnabled(False)
            self.rb_counting.setText("Зона подсчёта уже добавлена на эту камеру")
        type_layout.addWidget(self.rb_control)
        type_layout.addWidget(self.rb_counting)
        layout.addWidget(type_group)

        btns = QHBoxLayout()
        ok_btn = QPushButton("Создать")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)


    def zone_name(self) -> str:
        return self.name_edit.text().strip()

    def zone_type(self) -> str:
        return ZONE_TYPE_COUNTING if self.rb_counting.isChecked() else ZONE_TYPE_CONTROL


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
        self.zone_types = {}

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
            ztype = self.zone_types.get(i, ZONE_TYPE_CONTROL)
            palette = ZONE_COLORS[ztype]

            if i in self.active_zones:
                color = palette["active"]
                painter.setPen(QPen(color, 3))
                painter.setBrush(QColor(color.red(), color.green(), color.blue(), 35))
            else:
                color = palette["normal"]
                painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(color.red(), color.green(), color.blue(), 20))
            painter.drawRect(rect)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            name = self.zone_names[i] if i < len(self.zone_names) else f"Зона {i}"
            tag = " [счётчик]" if ztype == ZONE_TYPE_COUNTING else ""
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            painter.setPen(color)
            painter.drawText(rect.x() + 4, rect.y() + 14, name + tag)
            painter.setPen(QPen(color))

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

        def _reindex(d: dict) -> dict:
            d.pop(zone_index, None)
            return {(idx - 1 if idx > zone_index else idx): v for idx, v in d.items()}

        self.zone_rules = _reindex(self.zone_rules)
        self.zone_types = _reindex(self.zone_types)
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
                already_counting = any(
                    t == ZONE_TYPE_COUNTING for t in self.zone_types.values()
                )
                dlg = ZoneCreateDialog(
                    self,
                    default_name=f"Зона {len(self.zones)}",
                    counting_disabled=already_counting,
                )
                if not dlg.exec():
                    self.update()
                    return

                zone_name = dlg.zone_name() or f"Зона {len(self.zones)}"
                zone_type = dlg.zone_type()

                if self.frame_width > 0 and self.frame_height > 0:
                    scale_x = self.frame_width / self.width()
                    scale_y = self.frame_height / self.height()
                    x = int(rect.x() * scale_x)
                    y = int(rect.y() * scale_y)
                    w = int(rect.width() * scale_x)
                    h = int(rect.height() * scale_y)
                else:
                    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

                idx = len(self.zones)
                self.zones.append((x, y, w, h))
                self.zone_names.append(zone_name)
                self.zone_types[idx] = zone_type

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

    def set_zones(self, zones, zone_names=None, zone_rules=None, zone_types=None):
        self.zones = zones.copy()
        self.zone_names = zone_names.copy() if zone_names else [f"Зона {i}" for i in range(len(zones))]
        self.zone_rules = zone_rules.copy() if zone_rules else {}
        self.zone_types = zone_types.copy() if zone_types else {}
        self._recalc_display_zones()
        self.update()