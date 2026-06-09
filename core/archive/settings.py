"""
Конфигурация видеоархива. Хранится в config/archive.json в пользовательской
директории; при отсутствии создаётся со значениями по умолчанию.
"""

import json
import os
from dataclasses import dataclass, asdict

from app_paths import user_data_path, archive_root


def _config_file() -> str:
    return user_data_path("config", "archive.json")


@dataclass
class ArchiveSettings:
    enabled: bool = True                 # мастер-выключатель записи
    segment_seconds: int = 60            # длительность одного сегмента
    archive_dir: str = ""                # корень архива (по умолчанию app_paths.archive_root)
    max_age_days: int = 14               # удалять записи старше N дней (0 = выкл)
    max_gb: float = 25.0                 # лимит размера архива в ГБ (0 = выкл)
    min_free_gb: float = 10.0            # резерв свободного места на диске
    record_audio: bool = False           # писать ли звук (по умолчанию нет, -an)
    indexer_poll_seconds: int = 15       # период сканирования новых сегментов
    retention_poll_seconds: int = 300    # период очистки

    def __post_init__(self):
        if not self.archive_dir:
            self.archive_dir = archive_root()

    # экспоненциальный backoff перезапуска ffmpeg (секунды)
    @property
    def restart_backoff(self) -> tuple:
        return (2, 5, 10, 30, 60)


def load() -> ArchiveSettings:
    path = _config_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            known = ArchiveSettings.__dataclass_fields__.keys()
            data = {k: v for k, v in data.items() if k in known}
            return ArchiveSettings(**data)
        except Exception as e:
            print(f"[Archive] Ошибка чтения archive.json, использую дефолты: {e}")
    settings = ArchiveSettings()
    save(settings)
    return settings


def save(settings: ArchiveSettings) -> None:
    path = _config_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Archive] Ошибка сохранения archive.json: {e}")
