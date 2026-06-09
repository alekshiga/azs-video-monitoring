"""
Разрешение пути к бинарнику ffmpeg в dev- и собранном (PyInstaller) режимах.

Приоритет:
  1. Собранный бинарник рядом с программой (resource_path("ffmpeg", ...)) — frozen.
  2. Статический ffmpeg из пакета imageio-ffmpeg (dev и fallback).
  3. ffmpeg из системного PATH.

imageio-ffmpeg не поставляет ffprobe, поэтому длительность сегмента
индексатор вычисляет без него (по началу следующего сегмента / mtime).
"""

import glob
import os
import shutil

from app_paths import is_frozen, resource_path


_cached = {"ffmpeg": None}


def _frozen_candidates():
    # сюда spec кладёт бинарник: datas += [(ffmpeg_exe, 'ffmpeg')].
    # PyInstaller сохраняет родное имя (ffmpeg-win-x86_64-vN.exe), поэтому
    # сначала пробуем точные имена, затем ищем любой ffmpeg* в папке.
    ff_dir = resource_path("ffmpeg")
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = os.path.join(ff_dir, name)
        if os.path.isfile(p):
            return p
    matches = glob.glob(os.path.join(ff_dir, "ffmpeg*"))
    matches = [m for m in matches if os.path.isfile(m)]
    return matches[0] if matches else None


def _imageio_ffmpeg():
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    return None


def ffmpeg_exe() -> str | None:
    """Возвращает путь к ffmpeg или None, если он недоступен."""
    if _cached["ffmpeg"]:
        return _cached["ffmpeg"]

    candidate = None
    if is_frozen():
        candidate = _frozen_candidates()
    if not candidate:
        candidate = _imageio_ffmpeg()
    if not candidate:
        candidate = shutil.which("ffmpeg")

    _cached["ffmpeg"] = candidate
    return candidate


def has_ffmpeg() -> bool:
    return ffmpeg_exe() is not None
