from dataclasses import dataclass
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
        self.entered = 0   # всего ТС въехало в зону
        self.exited = 0    # всего ТС выехало из зоны

    def add_visit(self, visit: Visit):
        self.visits.append(visit)

    def conversion(self) -> Optional[float]:
        """
        Заехавши машины = выехавшие
        :return:
        """
        if self.entered == 0:
            return None
        return self.exited / self.entered

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
            "entered": self.entered,
            "exited": self.exited,
            "conversion": self.conversion(),
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
    def __init__(self, db=None, min_visit_duration: float = 3.0, exit_grace: float = 5.0):
        """
        :param db: экземпляр core.database.Database
        :param min_visit_duration: минимальная длительность визита для учёта в
            статистике длительностей. На файлах видео ускорено, поэтому
            по умолчанию 3 сек, а на реальной IP-камере лучше 30+ сек
        :param exit_grace: сколько секунд объект может отсутствовать в зоне,
            прежде чем визит будет считаться завершенным, служит для того чтобы предотвратить потери объектов
            из-за перекрытия, кратковременной потери трека и тд.
        """
        self.db = db
        self.min_visit_duration = min_visit_duration
        self.exit_grace = exit_grace
        self._zone_stats: dict[tuple, ZoneStats] = {}
        self._active: dict[tuple, tuple] = {}
        self._pending_exit: dict[tuple, float] = {}  # key -> время первого отсутствия
        self.session_start = datetime.now()

    def _ensure_zone(self, source_id, zone_index: int, zone_name: str) -> ZoneStats:
        zone_key = (source_id, zone_index)
        if zone_key not in self._zone_stats:
            self._zone_stats[zone_key] = ZoneStats(zone_index, zone_name or f"Зона {zone_index}")
        return self._zone_stats[zone_key]

    def record_entry(self, source_id, track_id: int, zone_index: int,
                     class_name: str, entered_at: float, zone_name: str = None):
        key = (source_id, track_id, zone_index)
        # Восстанавливаем трек
        self._pending_exit.pop(key, None)
        if key in self._active:
            return
        self._active[key] = (entered_at, class_name)

        # считаем, сколько тс заехало
        if class_name in VEHICLE_CLASSES:
            zs = self._ensure_zone(source_id, zone_index, zone_name)
            zs.entered += 1
            if self.db:
                self.db.insert_event(
                    source_id, zone_index, zs.zone_name, "entry",
                    class_name=class_name, track_id=track_id, ts=entered_at,
                )

    def record_exit(self, source_id, track_id: int, zone_index: int,
                    zone_name: str, exited_at: float):
        key = (source_id, track_id, zone_index)
        entry = self._active.pop(key, None)
        if entry is None:
            return

        entered_at, class_name = entry
        duration = exited_at - entered_at

        # баланс заехало = выехало)
        if class_name in VEHICLE_CLASSES:
            zs = self._ensure_zone(source_id, zone_index, zone_name)
            zs.exited += 1
            if self.db:
                self.db.insert_event(
                    source_id, zone_index, zone_name, "exit",
                    class_name=class_name, track_id=track_id, ts=exited_at,
                )

        # Фильтруем слишком короткие визиты для статистики длительностей
        if duration < self.min_visit_duration:
            return

        zs = self._ensure_zone(source_id, zone_index, zone_name)
        visit = Visit(
            zone_index=zone_index,
            zone_name=zone_name,
            class_name=class_name,
            track_id=track_id,
            entered_at=entered_at,
            exited_at=exited_at,
            duration=duration,
        )
        zs.add_visit(visit)

        if self.db:
            self.db.insert_visit(
                source_id, zone_index, zone_name, class_name, track_id,
                entered_at, exited_at, duration,
            )


    def update_presence(self, source_id, present_keys: set,
                        zone_names: list, current_time: float) -> int:
        """
        Обновляет статус присутствия объектов в зонах подсчета и закрывает
        завершённые визиты с учетом grace-периода

        Если клиент заехал на заправку, и фактически находится там, но
        трек объекта пропадает, начинаем отсчет grace-period, и только если объекта нет
        grace-period (задаётся в коде в конструкторе StatsTracker), то считаем что
        объект уехал
        """
        closed = 0
        for key in list(self._active):
            if key[0] != source_id:
                continue
            _, track_id, zone_index = key

            if (track_id, zone_index) in present_keys:
                self._pending_exit.pop(key, None)
                continue

            if key not in self._pending_exit:
                self._pending_exit[key] = current_time
                continue

            first_missing = self._pending_exit[key]
            if current_time - first_missing >= self.exit_grace:
                name = zone_names[zone_index] if zone_index < len(zone_names) else f"Зона {zone_index}"
                self._pending_exit.pop(key, None)
                self.record_exit(source_id, track_id, zone_index, name, first_missing)
                closed += 1
        return closed


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
            self._pending_exit.clear()
        else:
            for store in (self._zone_stats, self._active, self._pending_exit):
                for key in list(store):
                    if key[0] == source_id:
                        del store[key]
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
            lines.append(f"  Въехало ТС: {sm['entered']}  |  Выехало ТС: {sm['exited']}")
            if sm["conversion"] is not None:
                lines.append(f"  Конверсия (выезд/въезд): {sm['conversion'] * 100:.0f}%")
            lines.append(f"  Транспортных средств: {sm['total_vehicles']}")
            if sm["avg"] is not None:
                lines.append(f"  Среднее время в зоне: {self.format_duration(sm['avg'])}")
                lines.append(f"  Минимальное: {self.format_duration(sm['min'])}")
                lines.append(f"  Максимальное: {self.format_duration(sm['max'])}")
            for cls, cnt in sm["by_class"].items():
                lines.append(f"  {cls}: {cnt} шт.")
        return lines
