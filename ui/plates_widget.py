import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QDialog, QLineEdit
)

BLACK_COLOR = QColor(255, 224, 224)  # подсветка номеров из чёрного списка


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

    COLUMNS = ["Время", "Номер", "Статус"]

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

        # действия
        top = QHBoxLayout()
        self.refresh_btn = QPushButton("Обновить")
        self.black_btn = QPushButton("⛔ В чёрный список")
        self.remove_btn = QPushButton("Убрать из чёрного списка")
        self.snapshot_btn = QPushButton("Фото автомобиля")
        for b in (self.refresh_btn, self.black_btn, self.remove_btn, self.snapshot_btn):
            top.addWidget(b)
        top.addStretch()
        self.refresh_btn.clicked.connect(self.refresh)
        self.black_btn.clicked.connect(self._add_black)
        self.remove_btn.clicked.connect(self._remove_black)
        self.snapshot_btn.clicked.connect(self._open_snapshot)
        layout.addLayout(top)

        # ручное добавление номера в чёрный список
        manual = QHBoxLayout()
        manual.addWidget(QLabel("Добавить номер в чёрный список:"))
        self.plate_edit = QLineEdit()
        self.plate_edit.setMaximumWidth(160)
        self.plate_edit.setPlaceholderText("A123BC45")
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_manual)
        manual.addWidget(self.plate_edit)
        manual.addWidget(add_btn)
        manual.addStretch()
        layout.addLayout(manual)

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
        # уникальные номера, без дублей
        self._rows = self.db.unique_plates(limit=300)
        self.table.setRowCount(len(self._rows))
        for r, p in enumerate(self._rows):
            plate = p.get("plate", "")
            is_black = self.db.get_watch_status(plate) == "black"
            values = [
                p.get("plate_dt", ""),
                plate,
                "Чёрный список" if is_black else "",
            ]
            for c, v in enumerate(values):
                it = QTableWidgetItem(str(v))
                if is_black:
                    it.setBackground(QBrush(BLACK_COLOR))
                self.table.setItem(r, c, it)

    def _selected_plate(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def _add_black(self):
        p = self._selected_plate()
        if not p:
            QMessageBox.information(self, "Чёрный список", "Выберите номер в журнале.")
            return
        self.db.set_watch(p["plate"], "black")
        self.refresh()

    def _remove_black(self):
        p = self._selected_plate()
        if not p:
            QMessageBox.information(self, "Чёрный список", "Выберите номер в журнале.")
            return
        self.db.remove_watch(p["plate"])
        self.refresh()

    def _add_manual(self):
        from core.anpr import normalize_plate, is_valid_ru_plate
        plate = normalize_plate(self.plate_edit.text())
        if not is_valid_ru_plate(plate):
            QMessageBox.warning(self, "Неверный номер",
                                "Введите номер в формате A123BC45 "
                                "(буквы А, В, Е, К, М, Н, О, Р, С, Т, У, Х).")
            return
        self.db.set_watch(plate, "black")
        self.plate_edit.clear()
        self.refresh()

    def _open_snapshot(self):
        p = self._selected_plate()
        if not p:
            return
        path = p.get("snapshot")
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "Фото", "Фото для этого номера недоступно.")
            return
        SnapshotDialog(self, path, title=p.get("plate", "")).exec()
