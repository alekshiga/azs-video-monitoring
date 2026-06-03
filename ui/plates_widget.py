import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QDialog, QLineEdit
)

WATCH_COLORS = {
    "black": QColor(255, 224, 224),
    "white": QColor(224, 245, 224),
}


class SnapshotDialog(QDialog):
    def __init__(self, parent, image_path, title="Снимок"):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lbl = QLabel()
        pix = QPixmap(image_path)
        if not pix.isNull():
            if pix.width() > 1000:
                pix = pix.scaledToWidth(1000, Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(pix)
        else:
            lbl.setText("Снимок недоступен")
        lay.addWidget(lbl)
        b = QPushButton("Закрыть"); b.clicked.connect(self.accept)
        lay.addWidget(b)


class PlatesWidget(QWidget):
    COLUMNS = ["Время", "Номер", "Уверенность", "Статус", "Визитов/час"]

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
        self.refresh_btn = QPushButton("Обновить")
        self.black_btn = QPushButton("➖ В чёрный список")
        self.white_btn = QPushButton("➕ В белый список")
        self.remove_btn = QPushButton("Убрать из списков")
        self.snapshot_btn = QPushButton("Снимок")
        for b in (self.refresh_btn, self.black_btn, self.white_btn,
                  self.remove_btn, self.snapshot_btn):
            top.addWidget(b)
        top.addStretch()
        self.refresh_btn.clicked.connect(self.refresh)
        self.black_btn.clicked.connect(lambda: self._set_watch("black"))
        self.white_btn.clicked.connect(lambda: self._set_watch("white"))
        self.remove_btn.clicked.connect(self._remove_watch)
        self.snapshot_btn.clicked.connect(self._open_snapshot)
        layout.addLayout(top)

        # ручное добавление номера в список
        manual = QHBoxLayout()
        manual.addWidget(QLabel("Номер вручную:"))
        self.plate_edit = QLineEdit()
        self.plate_edit.setMaximumWidth(160)
        self.plate_edit.setPlaceholderText("A123BC45")
        add_black = QPushButton("в чёрный")
        add_white = QPushButton("в белый")
        add_black.clicked.connect(lambda: self._add_manual("black"))
        add_white.clicked.connect(lambda: self._add_manual("white"))
        manual.addWidget(self.plate_edit)
        manual.addWidget(add_black)
        manual.addWidget(add_white)
        manual.addStretch()
        layout.addLayout(manual)

        self.summary = QLabel()
        self.summary.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._open_snapshot)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

    def refresh(self):
        if not self.db:
            return
        self._rows = self.db.recent_plates(limit=300)
        self.table.setRowCount(len(self._rows))
        for r, p in enumerate(self._rows):
            plate = p.get("plate", "")
            watch = self.db.get_watch_status(plate)
            visits = self.db.plate_visit_count(plate, since=(p.get("ts") or 0) - 3600)
            status = {"black": "Чёрный список",
                      "white": "Белый список"}.get(watch, "")
            values = [
                p.get("plate_dt", ""),
                plate,
                f"{(p.get('confidence') or 0) * 100:.0f}%",
                status,
                str(visits),
            ]
            color = WATCH_COLORS.get(watch)
            for c, v in enumerate(values):
                it = QTableWidgetItem(str(v))
                if color:
                    it.setBackground(QBrush(color))
                self.table.setItem(r, c, it)
        self._update_summary()

    def _update_summary(self):
        total = len(self._rows)
        black = len(self.db.get_watchlist("black"))
        white = len(self.db.get_watchlist("white"))
        uniq = len({p.get("plate") for p in self._rows})
        self.summary.setText(
            f"Распознаваний: {total}  |  Уникальных номеров: {uniq}  |  "
            f"Чёрный список: {black}  |  Белый список: {white}"
        )

    def _selected_plate(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def _set_watch(self, list_type):
        p = self._selected_plate()
        if not p:
            QMessageBox.information(self, "Списки", "Выберите номер в журнале.")
            return
        self.db.set_watch(p["plate"], list_type)
        self.refresh()

    def _remove_watch(self):
        p = self._selected_plate()
        if not p:
            QMessageBox.information(self, "Списки", "Выберите номер в журнале.")
            return
        self.db.remove_watch(p["plate"])
        self.refresh()

    def _add_manual(self, list_type):
        from core.anpr import normalize_plate, is_valid_ru_plate
        raw = self.plate_edit.text()
        plate = normalize_plate(raw)
        if not is_valid_ru_plate(plate):
            QMessageBox.warning(self, "Неверный номер",
                                "Введите номер в формате A123BC45 (буквы А,В,Е,К,М,Н,О,Р,С,Т,У,Х).")
            return
        self.db.set_watch(plate, list_type)
        self.plate_edit.clear()
        self.refresh()

    def _open_snapshot(self):
        p = self._selected_plate()
        if not p:
            return
        path = p.get("snapshot")
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "Снимок", "Снимок недоступен.")
            return
        SnapshotDialog(self, path, title=p.get("plate", "")).exec()
