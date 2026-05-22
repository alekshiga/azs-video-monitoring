class ZoneRule:
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

class ConditionalRule:
    CONDITION_TYPES = {
        "has_car_no_person": "Машина есть, человека нет",
        "has_person_no_car": "Человек есть, машины нет",
        "has_both": "Есть и машина, и человек",
        "has_none": "Нет ни машины, ни человека",
        "has_car_only": "Только машина",
        "has_person_only": "Только человек"
    }

    def __init__(self, condition="has_person_no_car", duration=5, cooldown=60, enabled=True):
        self.condition = condition
        self.duration = duration
        self.cooldown = cooldown
        self.enabled = enabled

    def check(self, has_car, has_person, elapsed_time):
        condition_met = False

        if self.condition == "has_car_no_person":
            condition_met = has_car and not has_person
        elif self.condition == "has_person_no_car":
            condition_met = has_person and not has_car
        elif self.condition == "has_both":
            condition_met = has_car and has_person
        elif self.condition == "has_none":
            condition_met = not has_car and not has_person
        elif self.condition == "has_car_only":
            condition_met = has_car and not has_person
        elif self.condition == "has_person_only":
            condition_met = has_person and not has_car

        return condition_met and elapsed_time >= self.duration

    def to_dict(self):
        return {
            "type": "conditional",
            "condition": self.condition,
            "duration": self.duration,
            "cooldown": self.cooldown,
            "enabled": self.enabled
        }

    @staticmethod
    def from_dict(data):
        return ConditionalRule(
            condition=data.get("condition", "has_person_no_car"),
            duration=data.get("duration", 5),
            cooldown=data.get("cooldown", 60),
            enabled=data.get("enabled", True)
        )