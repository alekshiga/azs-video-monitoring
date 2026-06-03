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

                CREATE TABLE IF NOT EXISTS alerts (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id    INTEGER,
                    camera_name  TEXT,
                    zone_index   INTEGER,
                    zone_name    TEXT,
                    class_name   TEXT,
                    message      TEXT,
                    time_in_zone REAL,
                    snapshot     TEXT,
                    status       TEXT DEFAULT 'new',   -- new / acknowledged / resolved
                    ts           REAL,
                    alert_dt     TEXT,
                    ack_dt       TEXT,
                    resolved_dt  TEXT,
                    created_at   TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS plates (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id   INTEGER,
                    track_id    INTEGER,
                    plate       TEXT NOT NULL,
                    confidence  REAL,
                    snapshot    TEXT,
                    ts          REAL,
                    plate_dt    TEXT,
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS plate_watchlist (
                    plate       TEXT PRIMARY KEY,
                    list_type   TEXT NOT NULL,   -- black / white
                    note        TEXT,
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE INDEX IF NOT EXISTS idx_visits_src ON visits(source_id, zone_index);
                CREATE INDEX IF NOT EXISTS idx_events_src ON events(source_id, zone_index, event_type);
                CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
                CREATE INDEX IF NOT EXISTS idx_plates_plate ON plates(plate);
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

    def insert_plate(self, source_id, track_id, plate, confidence,
                     snapshot=None, ts=None) -> Optional[int]:
        """
        Записывает распознанный номер в журнал
        """
        ts = ts if ts is not None else time.time()
        plate_dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._lock:
                cur = self._conn.execute(
                    "INSERT INTO plates (source_id, track_id, plate, confidence, "
                    "snapshot, ts, plate_dt) VALUES (?,?,?,?,?,?,?)",
                    (source_id, track_id, plate, confidence, snapshot, ts, plate_dt),
                )
                self._conn.commit()
                return cur.lastrowid
        except Exception as e:
            print(f"[DB] Ошибка записи номера: {e}")
            return None

    def recent_plates(self, source_id=None, limit: int = 300) -> list[dict]:
        q = "SELECT * FROM plates"
        params = []
        if source_id is not None:
            q += " WHERE source_id=?"; params.append(source_id)
        q += " ORDER BY id DESC LIMIT ?"; params.append(limit)
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def plate_visit_count(self, plate: str, since: Optional[float] = None) -> int:
        """
        Кол-во появлений данных номеров на заправке
        """
        q = "SELECT COUNT(*) FROM plates WHERE plate=?"
        params = [plate]
        if since is not None:
            q += " AND ts>=?"; params.append(since)
        with self._lock:
            return self._conn.execute(q, params).fetchone()[0]

    def get_watch_status(self, plate: str) -> Optional[str]:
        """
        Возвращает black или white, если номер в списке, иначе None,
        но нужно нормальное качество для OCR
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT list_type FROM plate_watchlist WHERE plate=?", (plate,)
            ).fetchone()
        return row["list_type"] if row else None

    def set_watch(self, plate: str, list_type: str, note: str = "") -> None:
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO plate_watchlist (plate, list_type, note) VALUES (?,?,?) "
                    "ON CONFLICT(plate) DO UPDATE SET list_type=excluded.list_type, "
                    "note=excluded.note",
                    (plate, list_type, note),
                )
                self._conn.commit()
        except Exception as e:
            print(f"[DB] Ошибка watchlist: {e}")

    def remove_watch(self, plate: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM plate_watchlist WHERE plate=?", (plate,))
            self._conn.commit()

    def get_watchlist(self, list_type: Optional[str] = None) -> list[dict]:
        q = "SELECT * FROM plate_watchlist"
        params = []
        if list_type:
            q += " WHERE list_type=?"; params.append(list_type)
        q += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def insert_alert(self, source_id, camera_name, zone_index, zone_name,
                     class_name=None, message=None, time_in_zone=None,
                     snapshot=None, ts=None) -> Optional[int]:
        """
        Создаёт тревогу со статусом new
        """
        ts = ts if ts is not None else time.time()
        alert_dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._lock:
                cur = self._conn.execute(
                    "INSERT INTO alerts (source_id, camera_name, zone_index, zone_name, "
                    "class_name, message, time_in_zone, snapshot, status, ts, alert_dt) "
                    "VALUES (?,?,?,?,?,?,?,?,'new',?,?)",
                    (source_id, camera_name, zone_index, zone_name, class_name,
                     message, time_in_zone, snapshot, ts, alert_dt),
                )
                self._conn.commit()
                return cur.lastrowid
        except Exception as e:
            print(f"[DB] Ошибка записи тревоги: {e}")
            return None

    def get_alerts(self, status: Optional[str] = None, source_id=None,
                   limit: int = 300) -> list[dict]:
        """
        Список всех тревог + можно фильтровать по статусу
        """
        q = "SELECT * FROM alerts"
        conds, params = [], []
        if status:
            conds.append("status=?"); params.append(status)
        if source_id is not None:
            conds.append("source_id=?"); params.append(source_id)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def set_alert_status(self, alert_id: int, status: str) -> None:
        """
        Меняет статус тревоги и фиксирует время
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        col = {"acknowledged": "ack_dt", "resolved": "resolved_dt"}.get(status)
        try:
            with self._lock:
                if col:
                    self._conn.execute(
                        f"UPDATE alerts SET status=?, {col}=? WHERE id=?",
                        (status, now, alert_id),
                    )
                else:
                    self._conn.execute(
                        "UPDATE alerts SET status=? WHERE id=?", (status, alert_id),
                    )
                self._conn.commit()
        except Exception as e:
            print(f"[DB] Ошибка обновления тревоги: {e}")

    def count_alerts(self, status: Optional[str] = None) -> int:
        q = "SELECT COUNT(*) FROM alerts"
        params = []
        if status:
            q += " WHERE status=?"; params.append(status)
        with self._lock:
            return self._conn.execute(q, params).fetchone()[0]

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
