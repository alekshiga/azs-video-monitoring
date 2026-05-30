import json
import os
from core.zone_rules import ZoneRule


class ZoneManager:
    def __init__(self, camera_id=None):
        self.camera_id = camera_id
        self.zones = []
        self.zone_names = []
        self.zone_rules = {}

    def set_zones(self, zones, zone_names=None, zone_rules=None):
        self.zones = zones.copy()
        if zone_names:
            self.zone_names = zone_names.copy()
        else:
            self.zone_names = [f"Зона {i}" for i in range(len(zones))]
        if zone_rules:
            self.zone_rules = zone_rules.copy()
        else:
            self.zone_rules = {}

    def clear_zones(self):
        self.zones.clear()
        self.zone_names.clear()
        self.zone_rules.clear()

    def get_rules_for_zone(self, zone_index):
        return self.zone_rules.get(zone_index, [])

    def add_rule_to_zone(self, zone_index, rule):
        if zone_index not in self.zone_rules:
            self.zone_rules[zone_index] = []
        self.zone_rules[zone_index].append(rule)

    def remove_rule_from_zone(self, zone_index, rule_index):
        if zone_index in self.zone_rules:
            if 0 <= rule_index < len(self.zone_rules[zone_index]):
                self.zone_rules[zone_index].pop(rule_index)
                if not self.zone_rules[zone_index]:
                    del self.zone_rules[zone_index]

    def check_intersection(self, bbox, zone_index, min_ratio=0.1):
        if zone_index >= len(self.zones):
            return False

        x1, y1, w, h = bbox
        x2, y2 = x1 + w, y1 + h

        zx, zy, zw, zh = self.zones[zone_index]
        zx2, zy2 = zx + zw, zy + zh

        ix1 = max(x1, zx)
        iy1 = max(y1, zy)
        ix2 = min(x2, zx2)
        iy2 = min(y2, zy2)

        if ix2 <= ix1 or iy2 <= iy1:
            return False

        intersection_area = (ix2 - ix1) * (iy2 - iy1)
        object_area = w * h

        overlap_ratio = intersection_area / max(object_area, 1)

        return overlap_ratio >= min_ratio

    def get_all_intersections(self, bbox, min_ratio=0.1):
        result = []
        for i in range(len(self.zones)):
            if self.check_intersection(bbox, i, min_ratio):
                result.append(i)
        return result

    def save_to_file(self, filepath):
        data = {
            "camera_id": self.camera_id,
            "zones": []
        }

        for i, (x, y, w, h) in enumerate(self.zones):
            name = self.zone_names[i] if i < len(self.zone_names) else f"Зона {i}"
            rules = []
            if i in self.zone_rules:
                rules = [rule.to_dict() for rule in self.zone_rules[i]]

            data["zones"].append({
                "name": name,
                "x": x, "y": y, "w": w, "h": h,
                "rules": rules
            })

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

    def load_from_file(self, filepath):
        if not os.path.exists(filepath):
            return False

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.camera_id = data.get("camera_id")
            self.zones.clear()
            self.zone_names.clear()
            self.zone_rules.clear()

            for i, zone_data in enumerate(data.get("zones", [])):
                x = zone_data.get("x", 0)
                y = zone_data.get("y", 0)
                w = zone_data.get("w", 0)
                h = zone_data.get("h", 0)
                name = zone_data.get("name", f"Зона {len(self.zones)}")

                self.zones.append((x, y, w, h))
                self.zone_names.append(name)

                rules_data = zone_data.get("rules", [])
                if rules_data:
                    from core.zone_rules import ConditionalRule
                    self.zone_rules[i] = [
                        ConditionalRule.from_dict(r) if r.get("type") == "conditional" else ZoneRule.from_dict(r)
                        for r in rules_data
                    ]

            return True
        except Exception as e:
            print(f"Ошибка загрузки зон: {e}")
            return False