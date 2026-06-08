# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller-спека для системы видеомониторинга АЗС.

Собирает one-folder приложение со всем ML-стеком (PyTorch CUDA + YOLOv8 +
EasyOCR + OpenCV + PyQt6). torch автоматически использует GPU при наличии
видеокарты NVIDIA и переключается на CPU, если её нет.

Сборка:   pyinstaller AZS-Monitoring.spec --noconfirm
Результат: dist\\AZS-Monitoring\\AZS-Monitoring.exe
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

project_dir = os.path.abspath(os.getcwd())

datas = []
binaries = []
hiddenimports = []

# --- Встроенные ресурсы только для чтения ---
datas += [('yolov8m.pt', '.')]          # модель детекции
datas += [('config', 'config')]         # дефолтные конфиги (шаблоны)
datas += [('tools', 'tools')]           # mediamtx и пр.

# --- Тяжёлые пакеты собираем целиком (данные, бинарники, подмодули) ---
for pkg in ('ultralytics', 'easyocr', 'torch', 'torchvision'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# --- Метаданные пакетов (нужны для importlib.metadata / проверок версий) ---
for pkg in ('ultralytics', 'torch', 'torchvision', 'numpy', 'tqdm',
            'easyocr', 'Pillow', 'reportlab', 'matplotlib',
            'opencv-python', 'requests', 'python-dotenv'):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# --- Доп. подмодули, которые часто теряются при автоанализе ---
hiddenimports += collect_submodules('scipy')
hiddenimports += ['app_paths']

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', '_pytest', 'pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AZS-Monitoring',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI-приложение; для отладки временно поставь True
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # сюда можно указать путь к .ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AZS-Monitoring',
)
