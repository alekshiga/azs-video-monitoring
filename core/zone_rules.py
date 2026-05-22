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