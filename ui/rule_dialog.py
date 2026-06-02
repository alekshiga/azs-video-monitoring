from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QTabWidget, QWidget,
    QListWidget, QListWidgetItem, QMessageBox, QGroupBox, QRadioButton
)
from PyQt6.QtCore import Qt
from core.zone_rules import (
    ZoneRule, ConditionalRule, CONDITION_PRESETS, PRESENCE_CLASS_LABELS
)


def rule_to_text(rule):
    if isinstance(rule, ConditionalRule):
        status = "" if rule.enabled else " [откл]"
        return f"[Ситуация] {rule.describe()} — дольше {rule.duration}с, кулдаун {rule.cooldown}с{status}"
    else:
        label = ZoneRule.CLASS_LABELS.get(rule.class_name, rule.class_name)
        status = "" if rule.enabled else " [откл]"
        return f"[Класс] {label} — мин {rule.min_time}с, кулдаун {rule.cooldown}с{status}"


class AddRuleDialog(QDialog):
    """Диалог добавления/редактирования одного правила."""

    def __init__(self, parent=None, existing_rule=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить правило")
        self.setMinimumWidth(440)

        layout = QVBoxLayout()
        self.tabs = QTabWidget()

        self._build_simple_tab()
        self._build_conditional_tab()
        layout.addWidget(self.tabs)

        # Общие параметры
        layout.addWidget(QLabel("Задержка между уведомлениями (сек):"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(5, 3600)
        self.cooldown_spin.setValue(60)
        layout.addWidget(self.cooldown_spin)

        self.enabled_cb = QCheckBox("Правило активно")
        self.enabled_cb.setChecked(True)
        layout.addWidget(self.enabled_cb)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Добавить")
        self.save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        if existing_rule:
            self._load_rule(existing_rule)


    def _build_simple_tab(self):
        tab = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(QLabel("Тип объекта:"))
        self.class_combo = QComboBox()
        for key, label in ZoneRule.CLASS_LABELS.items():
            self.class_combo.addItem(label, key)
        lay.addWidget(self.class_combo)

        lay.addWidget(QLabel("Минимальное время в зоне (сек):"))
        self.time_spin = QSpinBox()
        self.time_spin.setRange(0, 3600)
        self.time_spin.setValue(5)
        lay.addWidget(self.time_spin)
        lay.addStretch()
        tab.setLayout(lay)
        self.tabs.addTab(tab, "По типу объекта")


    def _build_conditional_tab(self):
        tab = QWidget()
        lay = QVBoxLayout()

        preset_group = QGroupBox("Готовый сценарий")
        pg = QVBoxLayout()
        pg.addWidget(QLabel("Выберите типичную ситуацию:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("— Свой вариант —", None)
        for name in CONDITION_PRESETS:
            self.preset_combo.addItem(name, name)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        pg.addWidget(self.preset_combo)
        preset_group.setLayout(pg)
        lay.addWidget(preset_group)

        manual_group = QGroupBox("Условия (что должно быть в зоне)")
        mg = QVBoxLayout()

        row1 = QHBoxLayout()
        self.cond1_class = QComboBox()
        for key, label in PRESENCE_CLASS_LABELS.items():
            self.cond1_class.addItem(label, key)
        self.cond1_state = QComboBox()
        self.cond1_state.addItem("присутствует", True)
        self.cond1_state.addItem("отсутствует", False)
        row1.addWidget(self.cond1_class)
        row1.addWidget(self.cond1_state)
        mg.addLayout(row1)

        logic_row = QHBoxLayout()
        self.rb_and = QRadioButton("И (оба условия)")
        self.rb_or = QRadioButton("ИЛИ (хотя бы одно)")
        self.rb_and.setChecked(True)
        logic_row.addWidget(self.rb_and)
        logic_row.addWidget(self.rb_or)
        mg.addLayout(logic_row)

        self.cond2_enabled = QCheckBox("Добавить второе условие")
        self.cond2_enabled.setChecked(True)
        mg.addWidget(self.cond2_enabled)
        row2 = QHBoxLayout()
        self.cond2_class = QComboBox()
        for key, label in PRESENCE_CLASS_LABELS.items():
            self.cond2_class.addItem(label, key)
        self.cond2_state = QComboBox()
        self.cond2_state.addItem("присутствует", True)
        self.cond2_state.addItem("отсутствует", False)
        row2.addWidget(self.cond2_class)
        row2.addWidget(self.cond2_state)
        mg.addLayout(row2)

        manual_group.setLayout(mg)
        lay.addWidget(manual_group)

        lay.addWidget(QLabel("Условие должно держаться дольше (сек):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 3600)
        self.duration_spin.setValue(5)
        lay.addWidget(self.duration_spin)

        lay.addStretch()
        tab.setLayout(lay)
        self.tabs.addTab(tab, "По ситуации (машина/человек)")

        self.preset_combo.setCurrentIndex(1)

    def _apply_preset(self):
        name = self.preset_combo.currentData()
        if not name:
            return
        conditions, logic = CONDITION_PRESETS[name]
        # первое условие
        self._set_combo_data(self.cond1_class, conditions[0][0])
        self._set_combo_data(self.cond1_state, conditions[0][1])
        # второе условие
        if len(conditions) > 1:
            self.cond2_enabled.setChecked(True)
            self._set_combo_data(self.cond2_class, conditions[1][0])
            self._set_combo_data(self.cond2_state, conditions[1][1])
        else:
            self.cond2_enabled.setChecked(False)
        (self.rb_and if logic == "and" else self.rb_or).setChecked(True)

    @staticmethod
    def _set_combo_data(combo, value):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _load_rule(self, rule):
        if isinstance(rule, ConditionalRule):
            self.tabs.setCurrentIndex(1)
            self.preset_combo.setCurrentIndex(0)
            conds = rule.conditions
            if conds:
                self._set_combo_data(self.cond1_class, conds[0]["class"])
                self._set_combo_data(self.cond1_state, conds[0]["present"])
            if len(conds) > 1:
                self.cond2_enabled.setChecked(True)
                self._set_combo_data(self.cond2_class, conds[1]["class"])
                self._set_combo_data(self.cond2_state, conds[1]["present"])
            else:
                self.cond2_enabled.setChecked(False)
            (self.rb_and if rule.logic == "and" else self.rb_or).setChecked(True)
            self.duration_spin.setValue(rule.duration)
            self.cooldown_spin.setValue(rule.cooldown)
            self.enabled_cb.setChecked(rule.enabled)
        else:
            self.tabs.setCurrentIndex(0)
            self._set_combo_data(self.class_combo, rule.class_name)
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
            conditions = [(self.cond1_class.currentData(), self.cond1_state.currentData())]
            if self.cond2_enabled.isChecked():
                conditions.append((self.cond2_class.currentData(), self.cond2_state.currentData()))
            logic = "and" if self.rb_and.isChecked() else "or"
            return ConditionalRule(
                conditions=conditions,
                logic=logic,
                duration=self.duration_spin.value(),
                cooldown=self.cooldown_spin.value(),
                enabled=self.enabled_cb.isChecked(),
            )


class ZoneRulesDialog(QDialog):
    """Диалог управления правилами одной зоны - список + добавление/удаление."""

    def __init__(self, parent=None, zone_name="Зона", rules=None):
        super().__init__(parent)
        self.setWindowTitle(f"Правила зоны: {zone_name}")
        self.setMinimumWidth(520)
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
        dlg.save_btn.setText("Сохранить")
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
