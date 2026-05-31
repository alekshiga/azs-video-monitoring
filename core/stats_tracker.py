from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}


@dataclass
class Visit:
    """Один завершенный визит клиента"""
    zone_index: int
    zone_name: str
    class_name: str
    track_id: int
    entered_at: float       # timestamp
    exited_at: float        # timestamp
    duration: float         # секунды

    def duration_str(self) -> str:
        m, s = divmod(int(self.duration), 60)
        return f"{m} мин {s} сек" if m else f"{s} сек"


class ZoneStats:
    """Статистика по одной зоне"""

    def __init__(self, zone_index: int, zone_name: str):
        self.zone_index = zone_index
        self.zone_name = zone_name
        self.visits: list[Visit] = []

    def add_visit(self, visit: Visit):
        self.visits.append(visit)

    def vehicle_visits(self) -> list[Visit]:
        return [v for v in self.visits if v.class_name in VEHICLE_CLASSES]

    def count(self, class_name: Optional[str] = None) -> int:
        if class_name:
            return sum(1 for v in self.visits if v.class_name == class_name)
        return len(self.vehicle_visits())

    def avg_duration(self, class_name: Optional[str] = None) -> Optional[float]:
        visits = [v for v in self.visits if v.class_name == class_name] if class_name else self.vehicle_visits()
        if not visits:
            return None
        return sum(v.duration for v in visits) / len(visits)

    def min_duration(self, class_name: Optional[str] = None) -> Optional[float]:
        visits = [v for v in self.visits if v.class_name == class_name] if class_name else self.vehicle_visits()
        return min((v.duration for v in visits), default=None)

    def max_duration(self, class_name: Optional[str] = None) -> Optional[float]:
        visits = [v for v in self.visits if v.class_name == class_name] if class_name else self.vehicle_visits()
        return max((v.duration for v in visits), default=None)

    def summary(self) -> dict:
        vv = self.vehicle_visits()
        durations = [v.duration for v in vv]
        return {
            "zone_name": self.zone_name,
            "total_vehicles": len(vv),
            "avg": sum(durations) / len(durations) if durations else None,
            "min": min(durations, default=None),
            "max": max(durations, default=None),
            "by_class": {
                cls: self.count(cls)
                for cls in VEHICLE_CLASSES
                if self.count(cls) > 0
            },
        }


class StatsTracker:
    """
    Отслеживает завершённые визиты объектов по зонам
    """

    def __init__(self):
        self._zone_stats: dict[tuple, ZoneStats] = {}
        self._active: dict[tuple, tuple] = {}
        self.session_start = datetime.now()


    def record_entry(self, source_id, track_id: int, zone_index: int,
                     class_name: str, entered_at: float):
        key = (source_id, track_id, zone_index)
        if key not in self._active:
            self._active[key] = (entered_at, class_name)

    def record_exit(self, source_id, track_id: int, zone_index: int,
                    zone_name: str, exited_at: float):
        key = (source_id, track_id, zone_index)
        entry = self._active.pop(key, None)
        if entry is None:
            return

        entered_at, class_name = entry
        duration = exited_at - entered_at

        # Фильтруем слишком короткие визиты (меньше 30 секунд), вдруг клиент не заправился
        #//todo т.к. на файле видео почему-то ускорено, поставил 3 сек, но на IP-камере лучше поставить 30+ сек
        if duration < 3.0:
            return

        zone_key = (source_id, zone_index)
        if zone_key not in self._zone_stats:
            self._zone_stats[zone_key] = ZoneStats(zone_index, zone_name)

        visit = Visit(
            zone_index=zone_index,
            zone_name=zone_name,
            class_name=class_name,
            track_id=track_id,
            entered_at=entered_at,
            exited_at=exited_at,
            duration=duration,
        )
        self._zone_stats[zone_key].add_visit(visit)


    def cleanup_lost_tracks(self, source_id, active_track_ids: set,
                            zone_names: list, current_time: float):
        """Закрываем визиты треков которые пропали из кадра"""
        lost = [
            key for key in list(self._active)
            if key[0] == source_id and key[1] not in active_track_ids
        ]
        for key in lost:
            _, track_id, zone_index = key
            name = zone_names[zone_index] if zone_index < len(zone_names) else f"Зона {zone_index}"
            self.record_exit(source_id, track_id, zone_index, name, current_time)


    def get_zone_stats(self, source_id, zone_index: int) -> Optional[ZoneStats]:
        return self._zone_stats.get((source_id, zone_index))


    def get_all_stats(self, source_id) -> list[ZoneStats]:
        return [
            stats for (sid, _), stats in self._zone_stats.items()
            if sid == source_id
        ]


    def total_vehicles(self, source_id) -> int:
        return sum(s.count() for s in self.get_all_stats(source_id))


    def reset(self, source_id=None):
        if source_id is None:
            self._zone_stats.clear()
            self._active.clear()
        else:
            for key in list(self._zone_stats):
                if key[0] == source_id:
                    del self._zone_stats[key]
            for key in list(self._active):
                if key[0] == source_id:
                    del self._active[key]
        self.session_start = datetime.now()


    def format_duration(self, seconds: Optional[float]) -> str:
        if seconds is None:
            return "нет данных"
        m, s = divmod(int(seconds), 60)
        return f"{m} мин {s} сек" if m else f"{s} сек"


    def as_log_lines(self, source_id) -> list[str]:
        lines = []
        lines.append(f"Статистика с {self.session_start.strftime('%d.%m.%Y %H:%M')}")
        for stats in sorted(self.get_all_stats(source_id), key=lambda s: s.zone_index):
            sm = stats.summary()
            if sm["total_vehicles"] == 0:
                continue
            lines.append(f"")
            lines.append(f"Зона: {sm['zone_name']}")
            lines.append(f"  Транспортных средств: {sm['total_vehicles']}")
            if sm["avg"] is not None:
                lines.append(f"  Среднее время в зоне: {self.format_duration(sm['avg'])}")
                lines.append(f"  Минимальное: {self.format_duration(sm['min'])}")
                lines.append(f"  Максимальное: {self.format_duration(sm['max'])}")
            for cls, cnt in sm["by_class"].items():
                lines.append(f"  {cls}: {cnt} шт.")
        return lines
