import os
import time
import sqlite3
import threading
from datetime import datetime
from typing import Optional

from app_paths import user_data_path


class Database:
    """
    SQLite-хранилище событий и визитов системы мониторинга
    таблица events: все события (entry / exit / alert) по зонам
    таблица visits: завершённые визиты объектов в зонах (вход + выход + длительность)

    Данные переживают перезапуск приложения, что позволяет строить
    аналитику не только за текущий сеанс, но и за любой период
    """

    def __init__(self, db_path: str = None):
        db_path = db_path or user_data_path("data", "monitoring.db")
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

                CREATE TABLE IF NOT EXISTS segments (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id   INTEGER NOT NULL,
                    path        TEXT NOT NULL UNIQUE,
                    start_ts    REAL NOT NULL,    -- эпоха начала сегмента (из имени файла)
                    end_ts      REAL,            -- эпоха конца (start следующего / по mtime)
                    duration    REAL,
                    size_bytes  INTEGER,
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE INDEX IF NOT EXISTS idx_visits_src ON visits(source_id, zone_index);
                CREATE INDEX IF NOT EXISTS idx_events_src ON events(source_id, zone_index, event_type);
                CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
                CREATE INDEX IF NOT EXISTS idx_alerts_src_ts ON alerts(source_id, ts);
                CREATE INDEX IF NOT EXISTS idx_plates_plate ON plates(plate);
                CREATE INDEX IF NOT EXISTS idx_segments_src_ts ON segments(source_id, start_ts);
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

    def unique_plates(self, limit: int = 300) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT p.* FROM plates p "
                "JOIN (SELECT plate, MAX(id) AS mid FROM plates GROUP BY plate) g "
                "ON p.id = g.mid "
                "ORDER BY p.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

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


    def insert_segment(self, source_id, path, start_ts, end_ts=None,
                       duration=None, size_bytes=None) -> Optional[int]:
        """
        Регистрирует завершенный сегмент записи
        """
        try:
            with self._lock:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO segments "
                    "(source_id, path, start_ts, end_ts, duration, size_bytes) "
                    "VALUES (?,?,?,?,?,?)",
                    (source_id, path, start_ts, end_ts, duration, size_bytes),
                )
                self._conn.commit()
                return cur.lastrowid if cur.rowcount else None
        except Exception as e:
            print(f"[DB] Ошибка записи сегмента: {e}")
            return None

    def segment_paths(self, source_id) -> set:
        with self._lock:
            rows = self._conn.execute(
                "SELECT path FROM segments WHERE source_id=?", (source_id,)
            ).fetchall()
        return {r["path"] for r in rows}

    def segments_in_range(self, source_id, t0, t1) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM segments WHERE source_id=? "
                "AND start_ts < ? AND COALESCE(end_ts, start_ts + 86400) > ? "
                "ORDER BY start_ts",
                (source_id, t1, t0),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_segment_at(self, source_id, t) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM segments WHERE source_id=? AND start_ts <= ? "
                "AND COALESCE(end_ts, start_ts + 86400) > ? "
                "ORDER BY start_ts DESC LIMIT 1",
                (source_id, t, t),
            ).fetchone()
        return dict(row) if row else None

    def next_segment_after(self, source_id, t) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM segments WHERE source_id=? AND start_ts > ? "
                "ORDER BY start_ts ASC LIMIT 1",
                (source_id, t),
            ).fetchone()
        return dict(row) if row else None

    def archive_bounds(self, source_id) -> Optional[tuple]:
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(start_ts) AS a, MAX(COALESCE(end_ts, start_ts)) AS b "
                "FROM segments WHERE source_id=?",
                (source_id,),
            ).fetchone()
        if row and row["a"] is not None:
            return (row["a"], row["b"])
        return None

    def oldest_segments(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM segments ORDER BY start_ts ASC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def segments_older_than(self, cutoff_ts, limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM segments WHERE start_ts < ? ORDER BY start_ts ASC LIMIT ?",
                (cutoff_ts, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def total_archive_bytes(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) AS s FROM segments"
            ).fetchone()
        return int(row["s"] or 0)

    def delete_segment(self, segment_id: int) -> None:
        try:
            with self._lock:
                self._conn.execute("DELETE FROM segments WHERE id=?", (segment_id,))
                self._conn.commit()
        except Exception as e:
            print(f"[DB] Ошибка удаления сегмента: {e}")

    def alerts_in_range(self, source_id, t0, t1) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, source_id, ts, alert_dt, zone_name, class_name, message, snapshot "
                "FROM alerts WHERE source_id=? AND ts BETWEEN ? AND ? ORDER BY ts",
                (source_id, t0, t1),
            ).fetchall()
        return [dict(r) for r in rows]

    def nearest_alert(self, source_id, t, direction: int) -> Optional[dict]:
        if direction >= 0:
            q = ("SELECT * FROM alerts WHERE source_id=? AND ts > ? "
                 "ORDER BY ts ASC LIMIT 1")
        else:
            q = ("SELECT * FROM alerts WHERE source_id=? AND ts < ? "
                 "ORDER BY ts DESC LIMIT 1")
        with self._lock:
            row = self._conn.execute(q, (source_id, t)).fetchone()
        return dict(row) if row else None

    def close(self):
        try:
            with self._lock:
                self._conn.commit()
                self._conn.close()
            print("[DB] Хранилище закрыто")
        except Exception as e:
            print(f"[DB] Ошибка закрытия: {e}")
