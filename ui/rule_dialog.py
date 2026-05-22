from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QComboBox, QSpinBox, QCheckBox, QTabWidget, \
    QWidget
from core.zone_rules import ZoneRule, ConditionalRule


class RuleDialog(QDialog):
    def __init__(self, parent=None, existing_rule=None):
        super().__init__(parent)
        self.setWindowTitle("Настройка правила для зоны")
        self.setMinimumWidth(380)

        layout = QVBoxLayout()

        self.tab_widget = QTabWidget()

        self.simple_tab = QWidget()
        simple_layout = QVBoxLayout()

        simple_layout.addWidget(QLabel("Тип объекта:"))
        self.class_combo = QComboBox()
        self.class_combo.addItems(["person", "car", "truck", "motorcycle", "bus"])
        simple_layout.addWidget(self.class_combo)

        simple_layout.addWidget(QLabel("Минимальное время в зоне (сек):"))
        self.time_spin = QSpinBox()
        self.time_spin.setMinimum(0)
        self.time_spin.setMaximum(3600)
        self.time_spin.setValue(5)
        simple_layout.addWidget(self.time_spin)

        self.simple_tab.setLayout(simple_layout)

        self.conditional_tab = QWidget()
        cond_layout = QVBoxLayout()

        cond_layout.addWidget(QLabel("Условие:"))
        self.condition_combo = QComboBox()
        self.condition_combo.addItems([
            "Человек есть, машины нет",
            "Машина есть, человека нет",
            "Есть и машина, и человек",
            "Нет ни машины, ни человека"
        ])
        cond_layout.addWidget(self.condition_combo)

        cond_layout.addWidget(QLabel("Длительность выполнения условия (сек):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setMinimum(0)
        self.duration_spin.setMaximum(3600)
        self.duration_spin.setValue(5)
        cond_layout.addWidget(self.duration_spin)

        self.conditional_tab.setLayout(cond_layout)

        self.tab_widget.addTab(self.simple_tab, "По классу объекта")
        self.tab_widget.addTab(self.conditional_tab, "По ситуации (машина/человек)")

        layout.addWidget(self.tab_widget)

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
        if hasattr(rule, 'condition'):
            self.tab_widget.setCurrentIndex(1)
            condition_map = {
                "has_person_no_car": "Человек есть, машины нет",
                "has_car_no_person": "Машина есть, человека нет",
                "has_both": "Есть и машина, и человек",
                "has_none": "Нет ни машины, ни человека"
            }
            self.condition_combo.setCurrentText(condition_map.get(rule.condition, "Человек есть, машины нет"))
            self.duration_spin.setValue(rule.duration)
            self.cooldown_spin.setValue(rule.cooldown)
            self.enabled_checkbox.setChecked(rule.enabled)
        else:
            self.tab_widget.setCurrentIndex(0)
            idx = self.class_combo.findText(rule.class_name)
            if idx >= 0:
                self.class_combo.setCurrentIndex(idx)
            self.time_spin.setValue(rule.min_time)
            self.cooldown_spin.setValue(rule.cooldown)
            self.enabled_checkbox.setChecked(rule.enabled)

    def get_rule(self):
        if self.tab_widget.currentIndex() == 0:
            return ZoneRule(
                class_name=self.class_combo.currentText(),
                min_time=self.time_spin.value(),
                cooldown=self.cooldown_spin.value(),
                enabled=self.enabled_checkbox.isChecked()
            )
        else:
            condition_map = {
                "Человек есть, машины нет": "has_person_no_car",
                "Машина есть, человека нет": "has_car_no_person",
                "Есть и машина, и человек": "has_both",
                "Нет ни машины, ни человека": "has_none"
            }
            condition_text = self.condition_combo.currentText()
            condition = condition_map.get(condition_text, "has_person_no_car")

            return ConditionalRule(
                condition=condition,
                duration=self.duration_spin.value(),
                cooldown=self.cooldown_spin.value(),
                enabled=self.enabled_checkbox.isChecked()
            )