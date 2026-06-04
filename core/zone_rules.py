class ZoneRule:
    CLASS_LABELS = {
        "any": "Любой объект (нет движения)",
        "person": "Человек",
        "car": "Автомобиль",
        "truck": "Грузовик",
        "bus": "Автобус",
        "motorcycle": "Мотоцикл",
    }

    def __init__(self, class_name="person", min_time=0, cooldown=60, enabled=True):
        self.class_name = class_name
        self.min_time = min_time
        self.cooldown = cooldown
        self.enabled = enabled

    def to_dict(self):
        return {
            "class": self.class_name,
            "min_time": self.min_time,
            "cooldown": self.cooldown,
            "enabled": self.enabled
        }

    @staticmethod
    def from_dict(data):
        return ZoneRule(
            class_name=data.get("class", "person"),
            min_time=data.get("min_time", 0),
            cooldown=data.get("cooldown", 60),
            enabled=data.get("enabled", True)
        )


PRESENCE_CLASS_LABELS = {
    "vehicle": "Любой транспорт",
    "car": "Легковой автомобиль",
    "truck": "Грузовик",
    "bus": "Автобус",
    "motorcycle": "Мотоцикл",
    "person": "Человек",
}

CONDITION_PRESETS = {
    "Машина без человека": ([("vehicle", True), ("person", False)], "and"),
    "Человек без машины":  ([("person", True), ("vehicle", False)], "and"),
    "Машина и человек вместе": ([("vehicle", True), ("person", True)], "and"),
    "Человек ИЛИ транспорт в зоне": ([("person", True), ("vehicle", True)], "or"),
}


class ConditionalRule:
    """
    Ситуативное правило: тревога, когда в зоне выполнены некоторые условия
    присутствия/отсутствия классов, на протяжении какого-то времнеи
    """
    is_conditional = True

    def __init__(self, conditions=None, logic="and", duration=5, cooldown=60, enabled=True):
        self.conditions = self._normalize(conditions) or [{"class": "vehicle", "present": True}]
        self.logic = logic if logic in ("and", "or") else "and"
        self.duration = duration
        self.cooldown = cooldown
        self.enabled = enabled

    @staticmethod
    def _normalize(conditions):
        if not conditions:
            return []
        result = []
        for c in conditions:
            if isinstance(c, dict):
                result.append({"class": c.get("class", "vehicle"),
                               "present": bool(c.get("present", True))})
            else:  # кортеж/список (class, present)
                result.append({"class": c[0], "present": bool(c[1])})
        return result

    def condition_met(self, present_classes) -> bool:

        results = []
        for c in self.conditions:
            is_present = c["class"] in present_classes
            results.append(is_present if c["present"] else not is_present)
        if not results:
            return False
        return all(results) if self.logic == "and" else any(results)

    def check(self, present_classes, elapsed_time):
        """
        Совместимость: условие выполнено И удерживается дольше какого-то порога времени,
        чтобы не терять из кадра объекты
        :param elapsed_time: сколько секунд НЕПРЕРЫВНО выполняется условие
        """
        return self.condition_met(present_classes) and elapsed_time >= self.duration

    def describe(self):
        # Удобные условные правила
        parts = []
        for c in self.conditions:
            label = PRESENCE_CLASS_LABELS.get(c["class"], c["class"])
            state = "есть" if c["present"] else "нет"
            parts.append(f"{label}: {state}")
        op = " И " if self.logic == "and" else " ИЛИ "
        return op.join(parts)

    def to_dict(self):
        return {
            "type": "conditional",
            "conditions": self.conditions,
            "logic": self.logic,
            "duration": self.duration,
            "cooldown": self.cooldown,
            "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(data):
        # Новый формат
        if "conditions" in data:
            return ConditionalRule(
                conditions=data.get("conditions"),
                logic=data.get("logic", "and"),
                duration=data.get("duration", 5),
                cooldown=data.get("cooldown", 60),
                enabled=data.get("enabled", True),
            )

        # Старый формат правил
        legacy = data.get("condition", "has_person_no_car")
        mapping = {
            "has_car_no_person": ([("vehicle", True), ("person", False)], "and"),
            "has_person_no_car": ([("person", True), ("vehicle", False)], "and"),
            "has_both":          ([("vehicle", True), ("person", True)], "and"),
        }
        conds, logic = mapping.get(legacy, mapping["has_person_no_car"])
        return ConditionalRule(
            conditions=conds, logic=logic,
            duration=data.get("duration", 5),
            cooldown=data.get("cooldown", 60),
            enabled=data.get("enabled", True),
        )
