import os
import sys
import glob
import shutil
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "monitoring.db")
INCIDENTS = os.path.join(ROOT, "incidents")
ARCHIVE = os.path.join(ROOT, "archive")


def clear_db(wipe_watchlist=False):
    if not os.path.exists(DB_PATH):
        print(f"БД не найдена: {DB_PATH} (нечего чистить)")
        return
    conn = sqlite3.connect(DB_PATH)
    tables = ["events", "visits", "alerts", "plates", "segments"]
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
    removed = 0
    for sub in ("", "anpr_debug"):
        d = os.path.join(INCIDENTS, sub) if sub else INCIDENTS
        for f in glob.glob(os.path.join(d, "*.jpg")):
            try:
                os.remove(f)
                removed += 1
            except OSError:
                pass
    print(f"Удалено файлов снимков: {removed}")


def clear_video():
    if not os.path.isdir(ARCHIVE):
        print("Видеоархив пуст.")
        return
    removed = 0
    for name in os.listdir(ARCHIVE):
        if not name.startswith("cam"):
            continue
        cam_dir = os.path.join(ARCHIVE, name)
        for f in glob.glob(os.path.join(cam_dir, "**", "*.mp4"), recursive=True):
            try:
                os.remove(f)
                removed += 1
            except OSError:
                pass
        shutil.rmtree(cam_dir, ignore_errors=True)
    print(f"Удалено видеосегментов: {removed}")


if __name__ == "__main__":
    wipe_all = "--all" in sys.argv
    print("Очистка тестовых данных...")
    print("Флаги: --files (снимки), --video (видеоархив), --all (всё, включая watchlist)")
    clear_db(wipe_watchlist=wipe_all)
    if "--files" in sys.argv or wipe_all:
        clear_files()
    if "--video" in sys.argv or wipe_all:
        clear_video()
    print("Готово.")
