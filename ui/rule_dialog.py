from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QComboBox, QSpinBox, QCheckBox
from core.zone_rules import ZoneRule


class RuleDialog(QDialog):
    def __init__(self, parent=None, existing_rule=None):
        super().__init__(parent)
        self.setWindowTitle("Настройка правила для зоны")
        self.setMinimumWidth(300)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Тип объекта:"))

        self.class_combo = QComboBox()
        self.class_combo.addItems(["person", "car", "truck", "motorcycle", "bus"])
        layout.addWidget(self.class_combo)

        layout.addWidget(QLabel("Минимальное время в зоне (сек):"))

        self.time_spin = QSpinBox()
        self.time_spin.setMinimum(0)
        self.time_spin.setMaximum(3600)
        self.time_spin.setValue(5)
        layout.addWidget(self.time_spin)

        layout.addWidget(QLabel("Задержка между уведомлениями (сек):"))

        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setMinimum(10)
        self.cooldown_spin.setMaximum(3600)
        self.cooldown_spin.setValue(60)
        layout.addWidget(self.cooldown_spin)

        self.enabled_checkbox = QCheckBox("Правило активно")
        self.enabled_checkbox.setChecked(True)
        layout.addWidget(self.enabled_checkbox)

        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.accept)
        layout.addWidget(save_btn)

        self.setLayout(layout)

        if existing_rule:
            self._load_rule(existing_rule)

    def _load_rule(self, rule):
        index = self.class_combo.findText(rule.class_name)
        if index >= 0:
            self.class_combo.setCurrentIndex(index)
        self.time_spin.setValue(rule.min_time)
        self.cooldown_spin.setValue(rule.cooldown)
        self.enabled_checkbox.setChecked(rule.enabled)

    def get_rule(self):
        return ZoneRule(
            class_name=self.class_combo.currentText(),
            min_time=self.time_spin.value(),
            cooldown=self.cooldown_spin.value(),
            enabled=self.enabled_checkbox.isChecked()
        )