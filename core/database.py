import os
import time
import sqlite3
import threading
from datetime import datetime
from typing import Optional


class Database:
    """
    SQLite-хранилище событий и визитов системы мониторинга
    таблица events: все события (entry / exit / alert) по зонам
    таблица visits: завершённые визиты объектов в зонах (вход + выход + длительность)

    Данные переживают перезапуск приложения, что позволяет строить
    аналитику не только за текущий сеанс, но и за любой период
    """

    def __init__(self, db_path: str = "data/monitoring.db"):
        self.db_path = db_path
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        self._lock = threading.Lock()
        # пишем из потока VideoThread
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        print(f"[DB] Хранилище подключено: {db_path}")

    def _init_schema(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS visits (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id   INTEGER NOT NULL,
                    zone_index  INTEGER NOT NULL,
                    zone_name   TEXT,
                    class_name  TEXT,
                    track_id    INTEGER,
                    entered_at  REAL,
                    exited_at   REAL,
                    duration    REAL,
                    entered_dt  TEXT,
                    exited_dt   TEXT,
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id   INTEGER NOT NULL,
                    zone_index  INTEGER,
                    zone_name   TEXT,
                    event_type  TEXT NOT NULL,   -- entry / exit / alert
                    class_name  TEXT,
                    track_id    INTEGER,
                    message     TEXT,
                    ts          REAL,
                    event_dt    TEXT,
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE INDEX IF NOT EXISTS idx_visits_src ON visits(source_id, zone_index);
                CREATE INDEX IF NOT EXISTS idx_events_src ON events(source_id, zone_index, event_type);
            """)
            self._conn.commit()


    def insert_event(self, source_id, zone_index, zone_name, event_type,
                     class_name=None, track_id=None, ts=None, message=None):
        """
        Записывает одно событие
        """
        ts = ts if ts is not None else time.time()
        event_dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO events (source_id, zone_index, zone_name, event_type, "
                    "class_name, track_id, message, ts, event_dt) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (source_id, zone_index, zone_name, event_type,
                     class_name, track_id, message, ts, event_dt),
                )
                self._conn.commit()
        except Exception as e:
            print(f"[DB] Ошибка записи события: {e}")

    def insert_visit(self, source_id, zone_index, zone_name, class_name,
                     track_id, entered_at, exited_at, duration):
        """
        Записывает один завершённый визит
        """
        entered_dt = datetime.fromtimestamp(entered_at).strftime("%Y-%m-%d %H:%M:%S")
        exited_dt = datetime.fromtimestamp(exited_at).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO visits (source_id, zone_index, zone_name, class_name, "
                    "track_id, entered_at, exited_at, duration, entered_dt, exited_dt) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (source_id, zone_index, zone_name, class_name, track_id,
                     entered_at, exited_at, duration, entered_dt, exited_dt),
                )
                self._conn.commit()
        except Exception as e:
            print(f"[DB] Ошибка записи визита: {e}")

    def get_conversion(self, source_id, zone_index: Optional[int] = None,
                       since: Optional[float] = None) -> dict:
        """
        Конверсия по зоне подсчёта: сколько ТС въехало и сколько выехало
        :param source_id:
        :param zone_index:
        :param since:
        :return: {'entered': int, 'exited': int, 'rate': float/None}
                 rate - доля завершённых проездов (выехало / въехало)
        """
        q = ("SELECT event_type, COUNT(*) AS c FROM events "
             "WHERE source_id=? AND event_type IN ('entry','exit')")
        params = [source_id]
        if zone_index is not None:
            q += " AND zone_index=?"
            params.append(zone_index)
        if since is not None:
            q += " AND ts>=?"
            params.append(since)
        q += " GROUP BY event_type"

        with self._lock:
            rows = self._conn.execute(q, params).fetchall()

        counts = {r["event_type"]: r["c"] for r in rows}
        entered = counts.get("entry", 0)
        exited = counts.get("exit", 0)
        rate = (exited / entered) if entered else None
        return {"entered": entered, "exited": exited, "rate": rate}

    def get_visit_summary(self, source_id, since: Optional[float] = None) -> list[dict]:
        """
        Сводка по визитам из БД, сгруппированная по зонам
        """
        q = ("SELECT zone_index, zone_name, COUNT(*) AS total, "
             "AVG(duration) AS avg_d, MIN(duration) AS min_d, MAX(duration) AS max_d "
             "FROM visits WHERE source_id=?")
        params = [source_id]
        if since is not None:
            q += " AND exited_at>=?"
            params.append(since)
        q += " GROUP BY zone_index, zone_name ORDER BY zone_index"

        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, source_id, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE source_id=? ORDER BY id DESC LIMIT ?",
                (source_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        try:
            with self._lock:
                self._conn.commit()
                self._conn.close()
            print("[DB] Хранилище закрыто")
        except Exception as e:
            print(f"[DB] Ошибка закрытия: {e}")
