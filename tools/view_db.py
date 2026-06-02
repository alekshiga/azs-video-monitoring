import os
import sys
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "monitoring.db")


def main():
    if not os.path.exists(DB_PATH):
        print(f"БД не найдена: {DB_PATH}")
        print("Запусти приложение (main.py) и дай объектам зайти/выйти из зоны подсчёта.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    only = sys.argv[1] if len(sys.argv) > 1 else None

    if only in (None, "--events"):
        n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        print(f"\nevents: {n} строк (последние 15)")
        for r in conn.execute("SELECT event_dt, source_id, zone_name, event_type, "
                              "class_name, track_id, message FROM events "
                              "ORDER BY id DESC LIMIT 15"):
            print(f"{r['event_dt']} | cam{r['source_id']} | {r['zone_name']} | "
                  f"{r['event_type']:5} | {r['class_name']} #{r['track_id']} "
                  f"| {r['message'] or ''}")

    if only in (None, "--visits"):
        n = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
        print(f"\nvisits: {n} строк (последние 15)")
        for r in conn.execute("SELECT entered_dt, exited_dt, source_id, zone_name, "
                              "class_name, duration FROM visits "
                              "ORDER BY id DESC LIMIT 15"):
            print(f"{r['entered_dt']} -> {r['exited_dt']} | cam{r['source_id']} | "
                  f"{r['zone_name']} | {r['class_name']} | {r['duration']:.0f} сек")

    if only is None:
        print("\nКонверсия по зонам (за всё время)")
        rows = conn.execute(
            "SELECT source_id, zone_index, zone_name, "
            "SUM(event_type='entry') AS entered, SUM(event_type='exit') AS exited "
            "FROM events WHERE event_type IN ('entry','exit') "
            "GROUP BY source_id, zone_index ORDER BY source_id, zone_index"
        ).fetchall()
        for r in rows:
            entered, exited = r["entered"] or 0, r["exited"] or 0
            rate = f"{exited / entered * 100:.0f}%" if entered else "—"
            print(f"cam{r['source_id']} | {r['zone_name']}: "
                  f"въехало {entered}, выехало {exited}, конверсия {rate}")

    conn.close()


if __name__ == "__main__":
    main()
