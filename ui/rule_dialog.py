from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QTabWidget, QWidget,
    QListWidget, QListWidgetItem, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt
from core.zone_rules import ZoneRule, ConditionalRule


CONDITION_LABELS = {
    "has_person_no_car": "Человек есть, машины нет",
    "has_car_no_person": "Машина есть, человека нет",
    "has_both": "Есть и машина, и человек",
}
CONDITION_KEYS = {v: k for k, v in CONDITION_LABELS.items()}


def rule_to_text(rule):
    if isinstance(rule, ConditionalRule):
        label = CONDITION_LABELS.get(rule.condition, rule.condition)
        status = "" if rule.enabled else " [откл]"
        return f"[Ситуация] {label} — {rule.duration}с, кулдаун {rule.cooldown}с{status}"
    else:
        label = ZoneRule.CLASS_LABELS.get(rule.class_name, rule.class_name)
        status = "" if rule.enabled else " [откл]"
        return f"[Класс] {label} — мин {rule.min_time}с, кулдаун {rule.cooldown}с{status}"


class AddRuleDialog(QDialog):
    """Диалог добавления одного правила"""

    def __init__(self, parent=None, existing_rule=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить правило")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        self.tabs = QTabWidget()

        simple_tab = QWidget()
        simple_layout = QVBoxLayout()

        # Правило по типу объекта
        simple_layout.addWidget(QLabel("Тип объекта:"))
        self.class_combo = QComboBox()
        for key, label in ZoneRule.CLASS_LABELS.items():
            self.class_combo.addItem(label, key)
        simple_layout.addWidget(self.class_combo)

        simple_layout.addWidget(QLabel("Минимальное время в зоне (сек):"))
        self.time_spin = QSpinBox()
        self.time_spin.setRange(0, 3600)
        self.time_spin.setValue(5)
        simple_layout.addWidget(self.time_spin)

        simple_tab.setLayout(simple_layout)
        self.tabs.addTab(simple_tab, "По классу объекта")

        # Ситуативные правила
        cond_tab = QWidget()
        cond_layout = QVBoxLayout()

        cond_layout.addWidget(QLabel("Ситуация в зоне:"))
        self.condition_combo = QComboBox()
        for label in CONDITION_LABELS.values():
            self.condition_combo.addItem(label)
        cond_layout.addWidget(self.condition_combo)

        cond_layout.addWidget(QLabel("Длительность выполнения условия (сек):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 3600)
        self.duration_spin.setValue(5)
        cond_layout.addWidget(self.duration_spin)

        cond_tab.setLayout(cond_layout)
        self.tabs.addTab(cond_tab, "По ситуации (машина/человек)")

        layout.addWidget(self.tabs)

        layout.addWidget(QLabel("Задержка между уведомлениями (сек):"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(10, 3600)
        self.cooldown_spin.setValue(60)
        layout.addWidget(self.cooldown_spin)

        self.enabled_cb = QCheckBox("Правило активно")
        self.enabled_cb.setChecked(True)
        layout.addWidget(self.enabled_cb)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Добавить")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        if existing_rule:
            self._load_rule(existing_rule)

    def _load_rule(self, rule):
        if isinstance(rule, ConditionalRule):
            self.tabs.setCurrentIndex(1)
            label = CONDITION_LABELS.get(rule.condition, "")
            idx = self.condition_combo.findText(label)
            if idx >= 0:
                self.condition_combo.setCurrentIndex(idx)
            self.duration_spin.setValue(rule.duration)
            self.cooldown_spin.setValue(rule.cooldown)
            self.enabled_cb.setChecked(rule.enabled)
        else:
            self.tabs.setCurrentIndex(0)
            idx = self.class_combo.findData(rule.class_name)
            if idx >= 0:
                self.class_combo.setCurrentIndex(idx)
            self.time_spin.setValue(rule.min_time)
            self.cooldown_spin.setValue(rule.cooldown)
            self.enabled_cb.setChecked(rule.enabled)

    def get_rule(self):
        if self.tabs.currentIndex() == 0:
            return ZoneRule(
                class_name=self.class_combo.currentData(),
                min_time=self.time_spin.value(),
                cooldown=self.cooldown_spin.value(),
                enabled=self.enabled_cb.isChecked(),
            )
        else:
            label = self.condition_combo.currentText()
            condition = CONDITION_KEYS.get(label, "has_person_no_car")
            return ConditionalRule(
                condition=condition,
                duration=self.duration_spin.value(),
                cooldown=self.cooldown_spin.value(),
                enabled=self.enabled_cb.isChecked(),
            )


class ZoneRulesDialog(QDialog):
    """Диалог управления правилами одной зоны - список + добавление/удаление"""

    def __init__(self, parent=None, zone_name="Зона", rules=None):
        super().__init__(parent)
        self.setWindowTitle(f"Правила зоны: {zone_name}")
        self.setMinimumWidth(480)
        self.setMinimumHeight(320)

        self.rules = list(rules) if rules else []

        layout = QVBoxLayout()

        group = QGroupBox("Список правил (двойной клик - редактировать)")
        group_layout = QVBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(self._edit_rule)
        group_layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Добавить")
        add_btn.clicked.connect(self._add_rule)
        self.delete_btn = QPushButton("✕ Удалить")
        self.delete_btn.clicked.connect(self._delete_rule)
        self.toggle_btn = QPushButton("Вкл/Выкл")
        self.toggle_btn.clicked.connect(self._toggle_rule)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.toggle_btn)
        group_layout.addLayout(btn_row)

        group.setLayout(group_layout)
        layout.addWidget(group)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)
        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        for rule in self.rules:
            item = QListWidgetItem(rule_to_text(rule))
            if not rule.enabled:
                item.setForeground(Qt.GlobalColor.gray)
            self.list_widget.addItem(item)

    def _add_rule(self):
        dlg = AddRuleDialog(self)
        if dlg.exec():
            self.rules.append(dlg.get_rule())
            self._refresh_list()

    def _delete_rule(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        if QMessageBox.question(
            self, "Удаление", "Удалить выбранное правило?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.rules.pop(row)
            self._refresh_list()

    def _edit_rule(self, item):
        row = self.list_widget.row(item)
        dlg = AddRuleDialog(self, existing_rule=self.rules[row])
        dlg.setWindowTitle("Редактировать правило")
        
        for btn in dlg.findChildren(QPushButton):
            if btn.text() == "Добавить":
                btn.setText("Сохранить")
        if dlg.exec():
            self.rules[row] = dlg.get_rule()
            self._refresh_list()

    def _toggle_rule(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        rule = self.rules[row]
        rule.enabled = not rule.enabled
        self._refresh_list()
        self.list_widget.setCurrentRow(row)

    def get_rules(self):
        return self.rules
