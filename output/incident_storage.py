import os
from datetime import datetime

import cv2

INCIDENTS_DIR = "incidents"


def save_snapshot(frame, source_id, zone_index, directory: str = INCIDENTS_DIR):
    """
    Хранилище всех тревог
    :return: путь к файлу или None при ошибке
    """
    if frame is None:
        return None
    try:
        os.makedirs(directory, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"alert_cam{source_id}_zone{zone_index}_{ts}.jpg"
        path = os.path.join(directory, filename)

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        buf.tofile(path)
        return path
    except Exception as e:
        print(f"[Alerts] Ошибка сохранения снимка: {e}")
        return None
