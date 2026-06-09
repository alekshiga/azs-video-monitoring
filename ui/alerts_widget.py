import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QAbstractItemView, QMessageBox, QDialog
)

STATUS_LABELS = {
    "new": "🔴 Новая",
    "acknowledged": "🟡 Принята",
    "resolved": "🟢 Закрыта",
}
STATUS_COLORS = {
    "new": QColor(255, 235, 235),
    "acknowledged": QColor(255, 248, 225),
    "resolved": QColor(235, 245, 235),
}
FILTER_OPTIONS = [
    ("Все", None),
    ("🔴 Новые", "new"),
    ("🟡 Принятые", "acknowledged"),
    ("🟢 Закрытые", "resolved"),
]


class SnapshotDialog(QDialog):
    """Просмотр снимка инцидента"""

    def __init__(self, parent, image_path, title="Снимок инцидента"):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        label = QLabel()
        pix = QPixmap(image_path)
        if not pix.isNull():
            if pix.width() > 1000:
                pix = pix.scaledToWidth(1000, Qt.TransformationMode.SmoothTransformation)
            label.setPixmap(pix)
        else:
            label.setText("Не удалось загрузить снимок")
        layout.addWidget(label)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class AlertsWidget(QWidget):
    """
    Новый виджет с исторрией тревог, подгружает тревоги из БД
    """
    alerts_changed = pyqtSignal()
    alert_activated = pyqtSignal(int, float)   # source_id, ts — переход в архив

    COLUMNS = ["Время", "Камера", "Зона", "Объект", "Событие", "Статус"]

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._rows = []
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)


        top = QHBoxLayout()
        top.addWidget(QLabel("Фильтр:"))
        self.filter_combo = QComboBox()
        for label, _ in FILTER_OPTIONS:
            self.filter_combo.addItem(label)
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.filter_combo)

        top.addStretch()

        self.ack_btn = QPushButton("Принять")
        self.resolve_btn = QPushButton("Закрыть")
        self.snapshot_btn = QPushButton("Снимок")
        self.archive_btn = QPushButton("В архив")
        self.refresh_btn = QPushButton("Обновить")
        for b in (self.ack_btn, self.resolve_btn, self.snapshot_btn,
                  self.archive_btn, self.refresh_btn):
            top.addWidget(b)
        self.ack_btn.clicked.connect(self._acknowledge_selected)
        self.resolve_btn.clicked.connect(self._resolve_selected)
        self.snapshot_btn.clicked.connect(self._open_snapshot)
        self.archive_btn.clicked.connect(self._open_in_archive)
        self.refresh_btn.clicked.connect(self.refresh)

        layout.addLayout(top)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self.summary_label)

        # Таблица
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._open_snapshot)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

    def _current_filter(self):
        return FILTER_OPTIONS[self.filter_combo.currentIndex()][1]

    def refresh(self):
        if not self.db:
            return
        status = self._current_filter()
        self._rows = self.db.get_alerts(status=status)

        self.table.setRowCount(len(self._rows))
        for r, a in enumerate(self._rows):
            values = [
                a.get("alert_dt", ""),
                a.get("camera_name", ""),
                a.get("zone_name", ""),
                a.get("class_name", "") or "",
                a.get("message", "") or "",
                STATUS_LABELS.get(a.get("status"), a.get("status", "")),
            ]
            row_color = STATUS_COLORS.get(a.get("status"))
            for c, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if row_color:
                    item.setBackground(QBrush(row_color))
                self.table.setItem(r, c, item)

        self._update_summary()
        self.alerts_changed.emit()

    def _update_summary(self):
        new = self.db.count_alerts("new")
        ack = self.db.count_alerts("acknowledged")
        res = self.db.count_alerts("resolved")
        self.summary_label.setText(
            f"Новых: {new}   |   Принятых: {ack}   |   Закрытых: {res}   |   Всего: {new + ack + res}"
        )

    def new_count(self) -> int:
        return self.db.count_alerts("new") if self.db else 0

    def _selected_alert(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def _acknowledge_selected(self):
        a = self._selected_alert()
        if not a:
            QMessageBox.information(self, "Тревоги", "Выберите тревогу в списке.")
            return
        if a["status"] == "resolved":
            QMessageBox.information(self, "Тревоги", "Тревога уже закрыта.")
            return
        self.db.set_alert_status(a["id"], "acknowledged")
        self.refresh()

    def _resolve_selected(self):
        a = self._selected_alert()
        if not a:
            QMessageBox.information(self, "Тревоги", "Выберите тревогу в списке.")
            return
        self.db.set_alert_status(a["id"], "resolved")
        self.refresh()

    def _open_in_archive(self):
        a = self._selected_alert()
        if not a:
            QMessageBox.information(self, "Тревоги", "Выберите тревогу в списке.")
            return
        sid = a.get("source_id")
        ts = a.get("ts")
        if sid is None or ts is None:
            QMessageBox.information(self, "Архив", "Для этой тревоги нет времени для перехода.")
            return
        self.alert_activated.emit(int(sid), float(ts))

    def _open_snapshot(self):
        a = self._selected_alert()
        if not a:
            return
        path = a.get("snapshot")
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "Снимок", "Снимок для этой тревоги недоступен.")
            return
        SnapshotDialog(self, path, title=f"{a.get('camera_name', '')} — {a.get('zone_name', '')}").exec()
