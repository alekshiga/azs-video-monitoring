import os
import sys
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "monitoring.db")
INCIDENTS = os.path.join(ROOT, "incidents")


def clear_db(wipe_watchlist=False):
    if not os.path.exists(DB_PATH):
        print(f"БД не найдена: {DB_PATH} (нечего чистить)")
        return
    conn = sqlite3.connect(DB_PATH)
    tables = ["events", "visits", "alerts", "plates"]
    if wipe_watchlist:
        tables.append("plate_watchlist")
    for t in tables:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            conn.execute(f"DELETE FROM {t}")
            print(f"  {t}: удалено {n} записей")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("DELETE FROM sqlite_sequence")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.execute("VACUUM")
    conn.commit()
    conn.close()
    print("База данных очищена.")


def clear_files():
    import glob
    removed = 0
    for sub in ("", "anpr_debug"):
        d = os.path.join(INCIDENTS, sub) if sub else INCIDENTS
        for f in glob.glob(os.path.join(d, "*.jpg")):
            try:
                os.remove(f); removed += 1
            except OSError:
                pass
    print(f"Удалено файлов снимков: {removed}")


if __name__ == "__main__":
    wipe_all = "--all" in sys.argv
    print("Очистка тестовых данных...")
    clear_db(wipe_watchlist=wipe_all)
    if "--files" in sys.argv or wipe_all:
        clear_files()
    print("Готово.")
