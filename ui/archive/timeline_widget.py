"""
TimelineWidget — масштабируемая шкала времени архива (как в Trassir/Macroscop).

Слои отрисовки:
  • серые полосы   — доступная запись (сегменты);
  • красные метки  — тревоги;
  • синяя линия    — текущая позиция воспроизведения (playhead);
  • деления времени с подписями.

Взаимодействие:
  • колесо мыши  — зум вокруг курсора;
  • перетаскивание — панорама;
  • клик         — seek_requested(epoch).
"""

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtWidgets import QWidget


class TimelineWidget(QWidget):
    seek_requested = pyqtSignal(float)          # epoch seconds
    range_changed = pyqtSignal(float, float)    # видимый интервал изменился

    MIN_SPAN = 30.0           # минимальная ширина окна, сек (макс. зум)
    MAX_SPAN = 14 * 86400.0   # максимальная ширина окна, сек

    BG = QColor(40, 44, 52)
    SEG = QColor(90, 160, 90)
    SEG_HOVER = QColor(120, 200, 120)
    ALERT = QColor(220, 70, 70)
    PLAYHEAD = QColor(80, 170, 255)
    RULER = QColor(150, 150, 150)
    TEXT = QColor(210, 210, 210)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(90)
        self.setMouseTracking(True)

        now = datetime.now().timestamp()
        self._t0 = now - 3600.0
        self._t1 = now
        self._segments = []
        self._alerts = []
        self._playhead = None

        self._drag_x = None
        self._drag_t0 = None
        self._hover_x = None

    # ------------------------------------------------------------------ #
    #  Внешний API                                                        #
    # ------------------------------------------------------------------ #

    def set_segments(self, segs):
        self._segments = segs or []
        self.update()

    def set_alerts(self, alerts):
        self._alerts = alerts or []
        self.update()

    def set_view(self, t0, t1):
        if t1 - t0 < self.MIN_SPAN:
            t1 = t0 + self.MIN_SPAN
        self._t0, self._t1 = t0, t1
        self.range_changed.emit(t0, t1)
        self.update()

    def view_range(self):
        return self._t0, self._t1

    def set_playhead(self, t):
        self._playhead = t
        # автопрокрутка, если playhead вышел за видимую область
        if t is not None and (t < self._t0 or t > self._t1):
            span = self._t1 - self._t0
            self.set_view(t - span / 2, t + span / 2)
        else:
            self.update()

    # ------------------------------------------------------------------ #
    #  Преобразование время<->пиксель                                     #
    # ------------------------------------------------------------------ #

    def _t_to_x(self, t):
        span = self._t1 - self._t0
        if span <= 0:
            return 0
        return (t - self._t0) / span * self.width()

    def _x_to_t(self, x):
        span = self._t1 - self._t0
        return self._t0 + (x / max(1, self.width())) * span

    # ------------------------------------------------------------------ #
    #  Отрисовка                                                          #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, self.BG)

        track_top = 20
        track_h = h - 40
        track_bottom = track_top + track_h

        # сегменты записи
        for sg in self._segments:
            st = sg.get("start_ts")
            en = sg.get("end_ts") or (st + (sg.get("duration") or 0))
            if en < self._t0 or st > self._t1:
                continue
            x0 = self._t_to_x(max(st, self._t0))
            x1 = self._t_to_x(min(en, self._t1))
            p.fillRect(QRectF(x0, track_top, max(1.0, x1 - x0), track_h),
                       QBrush(self.SEG))

        # тревоги (метки)
        p.setPen(QPen(self.ALERT, 2))
        for a in self._alerts:
            ts = a.get("ts")
            if ts is None or ts < self._t0 or ts > self._t1:
                continue
            x = self._t_to_x(ts)
            p.drawLine(int(x), track_top, int(x), track_bottom)
            p.setBrush(QBrush(self.ALERT))
            p.drawEllipse(QRectF(x - 3, track_top - 4, 6, 6))

        self._draw_ruler(p, track_top, track_bottom)

        # playhead
        if self._playhead is not None and self._t0 <= self._playhead <= self._t1:
            x = self._t_to_x(self._playhead)
            p.setPen(QPen(self.PLAYHEAD, 2))
            p.drawLine(int(x), 0, int(x), h)

        # подсказка времени под курсором
        if self._hover_x is not None:
            p.setPen(QPen(QColor(120, 120, 120), 1, Qt.PenStyle.DashLine))
            p.drawLine(self._hover_x, track_top, self._hover_x, track_bottom)
            self._draw_label(p, self._hover_x, self._x_to_t(self._hover_x), top=True)

        p.end()

    def _nice_step(self, span):
        # подобрать шаг делений под текущий масштаб
        targets = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600,
                   7200, 10800, 21600, 43200, 86400]
        approx = span / 8.0
        for s in targets:
            if s >= approx:
                return s
        return 86400

    def _draw_ruler(self, p, top, bottom):
        span = self._t1 - self._t0
        step = self._nice_step(span)
        p.setPen(QPen(self.RULER, 1))
        p.setFont(QFont("Segoe UI", 7))

        start = self._t0 - (self._t0 % step) + step
        t = start
        while t < self._t1:
            x = int(self._t_to_x(t))
            p.setPen(QPen(self.RULER, 1))
            p.drawLine(x, top, x, top + 6)
            p.drawLine(x, bottom - 6, x, bottom)
            self._draw_label(p, x, t, top=False)
            t += step

    def _draw_label(self, p, x, t, top):
        dt = datetime.fromtimestamp(t)
        span = self._t1 - self._t0
        if span <= 3600:
            text = dt.strftime("%H:%M:%S")
        elif span <= 86400:
            text = dt.strftime("%H:%M")
        else:
            text = dt.strftime("%d.%m %H:%M")
        p.setPen(QPen(self.TEXT, 1))
        p.setFont(QFont("Segoe UI", 7))
        rect = QRectF(x - 40, 2 if top else self.height() - 16, 80, 14)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------------ #
    #  Мышь                                                               #
    # ------------------------------------------------------------------ #

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 0.8 if delta > 0 else 1.25
        cursor_t = self._x_to_t(event.position().x())
        span = (self._t1 - self._t0) * factor
        span = max(self.MIN_SPAN, min(self.MAX_SPAN, span))
        frac = (cursor_t - self._t0) / max(1e-6, (self._t1 - self._t0))
        new_t0 = cursor_t - span * frac
        self.set_view(new_t0, new_t0 + span)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_x = event.position().x()
            self._drag_t0 = self._t0
            self._drag_moved = False

    def mouseMoveEvent(self, event):
        x = event.position().x()
        self._hover_x = int(x)
        if self._drag_x is not None:
            dx = x - self._drag_x
            if abs(dx) > 3:
                self._drag_moved = True
            span = self._t1 - self._t0
            shift = -dx / max(1, self.width()) * span
            self.set_view(self._drag_t0 + shift, self._drag_t0 + shift + span)
        else:
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_x is not None:
            if not getattr(self, "_drag_moved", False):
                # это клик, а не панорама — seek
                self.seek_requested.emit(self._x_to_t(event.position().x()))
            self._drag_x = None
            self._drag_t0 = None

    def leaveEvent(self, event):
        self._hover_x = None
        self.update()
