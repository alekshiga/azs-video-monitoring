class ZoneManager:
    def __init__(self):
        self.zones = []
        self.zone_names = []

    def set_zones(self, zones, zone_names=None):
        """
        Задать отслеживаемые зоны
        """
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
        """
        Возвращает список индексов зон, с которыми пересекается объект
        """
        result = []
        for i in range(len(self.zones)):
            if self.check_intersection(bbox, i, min_ratio):
                result.append(i)
        return result
