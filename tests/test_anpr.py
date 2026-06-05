import os
import tempfile

from core.anpr import normalize_plate, is_valid_ru_plate
from core.database import Database


def test_normalize_and_validate():
    # кириллица -> латиница, нижний регистр, мусорные символы
    assert normalize_plate("а123вс45") == "A123BC45"
    assert normalize_plate(" Х001УХ 199 ") == "X001YX199"
    assert is_valid_ru_plate("A123BC45")
    assert is_valid_ru_plate("X001YX199")
    assert not is_valid_ru_plate("ABC123")       # не тот формат
    assert not is_valid_ru_plate("A123BC")       # нет региона
    print("OK normalize/validate")


def test_db_plates_and_watchlist():
    path = os.path.join(tempfile.gettempdir(), "anpr_test.db")
    for ext in ("", "-wal", "-shm"):
        try:
            os.remove(path + ext)
        except OSError:
            pass
    db = Database(path)
    # журнал
    db.insert_plate(1, 10, "A123BC45", 0.91, ts=1000.0)
    db.insert_plate(1, 11, "A123BC45", 0.88, ts=1500.0)
    db.insert_plate(1, 12, "X001YX199", 0.95, ts=1600.0)
    assert len(db.recent_plates(1)) == 3

    # watchlist
    db.set_watch("A123BC45", "black", "должник")
    assert db.get_watch_status("A123BC45") == "black"
    assert db.get_watch_status("X001YX199") is None
    db.set_watch("X001YX199", "white", "свой")
    assert len(db.get_watchlist()) == 2
    assert len(db.get_watchlist("black")) == 1
    db.remove_watch("A123BC45")
    assert db.get_watch_status("A123BC45") is None
    db.close()
    print("OK db plates/watchlist")


if __name__ == "__main__":
    test_normalize_and_validate()
    test_db_plates_and_watchlist()
    print("ALL ANPR TESTS PASSED")
