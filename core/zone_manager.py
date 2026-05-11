import json
import os


class ZoneManager:
    def __init__(self, camera_id = None):
        self.camera_id = camera_id
        self.zones = []
        self.zone_names = []

    def set_zones(self, zones, zone_names=None):
        """Задать отслеживаемые зоны"""
        self.zones = zones.copy()
        if zone_names:
            self.zone_names = zone_names.copy()
        else:
            self.zone_names = [f"Зона {i}" for i in range(len(zones))]

    def clear_zones(self):
        self.zones.clear()
        self.zone_names.clear()

    def check_intersection(self, bbox, zone_index, min_ratio=0.1):
        """
        Проверяет пересечение bbox объекта с отслеживаемой зоной
        :param bbox: (x, y, w, h) объекта
        :param zone_index: индекс зоны
        :param min_ratio: минимальная доля пересечения (10%)
        :return: True если пересекается достаточно, иначе False
        """
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
            return False  # нет пересечения

        # noinspection PyUnresolvedReferences
        intersection_area = (ix2 - ix1) * (iy2 - iy1)
        object_area = w * h

        overlap_ratio = intersection_area / max(object_area, 1)

        return overlap_ratio >= min_ratio

    def get_all_intersections(self, bbox, min_ratio=0.1):
        """Возвращает список индексов зон, с которыми пересекается объект"""
        result = []
        for i in range(len(self.zones)):
            if self.check_intersection(bbox, i, min_ratio):
                result.append(i)
        return result

    def save_to_file(self, filepath):
        """Сохранить зоны в JSON файл"""
        data = {
            "camera_id": self.camera_id,
            "zones": []
        }

        for i, (x, y, w, h) in enumerate(self.zones):
            name = self.zone_names[i] if i < len(self.zone_names) else f"Зона {i}"
            data["zones"].append({
                "name": name,
                "x": x, "y": y, "w": w, "h": h
            })

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

    def load_from_file(self, filepath):
        """Загрузить зоны из файла"""
        if not os.path.exists(filepath):
            return False

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.camera_id = data.get("camera_id")
            self.zones.clear()
            self.zone_names.clear()

            for zone_data in data.get("zones", []):
                x = zone_data.get("x", 0)
                y = zone_data.get("y", 0)
                w = zone_data.get("w", 0)
                h = zone_data.get("h", 0)
                name = zone_data.get("name", f"Зона {len(self.zones)}")

                self.zones.append((x, y, w, h))
                self.zone_names.append(name)

            return True
        except Exception as e:
            print(f"Ошибка загрузки зон: {e}")
            return False