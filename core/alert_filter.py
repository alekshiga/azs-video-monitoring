import time

class AlertFilter:
    def __init__(self, min_presence_time=2.0, alert_cooldown=30.0, min_ratio=0.1):
        """
        :param min_presence_time: минимальное время в зоне для тревоги (2 секунды)
        :param alert_cooldown: задержка между тревогами из одной зоны (30 секунд)
        :param min_ratio: минимальная доля пересечения с отслеживаемой зоной (0.1 = 15%)
        """
        self.min_presence_time = min_presence_time
        self.alert_cooldown = alert_cooldown
        self.min_overlap_ratio = min_ratio

        # Хранилища
        self.track_zone_entry = {}    # время входа объекта в отслеживаемую зону
        self.zone_last_alert = {}     # время последней тревоги из отслеживаемой зоны

        # Статистика
        self.total_alerts = 0
        self.total_ignored = 0

    def reset(self):
        self.track_zone_entry.clear()
        self.zone_last_alert.clear()
        self.total_alerts = 0
        self.total_ignored = 0

    def process_object(self, track_id, zone_index, current_time, in_zone):
        """
        Обработка одного объекта
        :param track_id: ID объекта
        :param zone_index: индекс зоны
        :param current_time: текущее время
        :param in_zone: находится ли объект в зоне
        :return: True если нужно вызвать тревогу
        """
        if track_id is None:
            return False

        key = (track_id, zone_index)

        if not in_zone:
            """
            Если бъект вышел из зоны вышел из зоны, то забываем его время,
            на случай если объект на мгновение зайдёт в отслеживаемую зону (баг трекинга/детекции)
            """
            self.track_zone_entry.pop(key, None)
            return False

        if key not in self.track_zone_entry:
            self.track_zone_entry[key] = current_time
            return False

        # Проверяем, сколько времени объект находится в отслеживаемой зоне
        time_in_zone = current_time - self.track_zone_entry[key]

        if time_in_zone < self.min_presence_time:
            return False

        # Проверяем кулдаун для зоны
        last_alert = self.zone_last_alert.get(zone_index, 0)
        if current_time - last_alert < self.alert_cooldown:
            self.total_ignored += 1
            return False

        self.zone_last_alert[zone_index] = current_time
        self.total_alerts += 1
        return True

    def process_frame(self, objects, zone_manager):
        """
        Обрабатывает все объекты на кадре
        :param objects: список объектов от детектора
        :param zone_manager: ZoneManager для проверки пересечений
        :return: список индексов зон, где нужна тревога
        """
        current_time = time.time()
        alert_zones = set()

        for obj in objects:
            track_id = obj.get('track_id')
            bbox = obj.get('bbox')
            obj.get('area', 0)

            if track_id is None or bbox is None:
                continue

            # Ищем все зоны, с которыми пересекается объект
            intersecting_zones = zone_manager.get_all_intersections(
                bbox, self.min_overlap_ratio
            )

            for zone_idx in intersecting_zones:
                if self.process_object(track_id, zone_idx, current_time, in_zone=True):
                    alert_zones.add(zone_idx)
                    
            for zone_idx in range(len(zone_manager.zones)):
                if zone_idx not in intersecting_zones:
                    key = (track_id, zone_idx)
                    if key in self.track_zone_entry:
                        self.process_object(track_id, zone_idx, current_time, in_zone=False)

        return list(alert_zones)

    def get_stats_text(self):
        return f"Тревог: {self.total_alerts} | Игнорировано: {self.total_ignored}"