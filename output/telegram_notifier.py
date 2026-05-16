import os
import threading
import time
from datetime import datetime

import cv2
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()


class TelegramNotifier:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.cooldown = float(os.getenv("TELEGRAM_COOLDOWN_SECONDS", "10.0"))
        self.last_sent_time = {}
        self.enabled = True
        self._lock = threading.Lock()
        self.total_sent = 0
        self.total_errors = 0

    def send_alert(self, zone_index, zone_name=None, frame=None):
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False
        with self._lock:
            now = time.time()
            if now - self.last_sent_time.get(zone_index, 0) < self.cooldown:
                return False
            self.last_sent_time[zone_index] = now
        threading.Thread(target=self._send_alert_impl, args=(zone_index, zone_name, frame), daemon=True).start()
        return True

    def _send_alert_impl(self, zone_index, zone_name=None, frame=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = zone_name or f"Зона {zone_index}"
        try:
            if frame is not None and frame.size > 0:
                caption = f"Внимание\nЗона: {name}\nВремя: {timestamp}\nДвижение в запретной зоне"
                self._send_photo(caption, frame)
            else:
                self._send_text_alert(name, timestamp)
            self.total_sent += 1
            print(f"[Telegram] Отправлено: {name}")
        except Exception as e:
            self.total_errors += 1
            print(f"[Telegram] Ошибка: {e}")
            try:
                self._send_text_alert(name, timestamp)
                self.total_sent += 1
            except Exception as e2:
                print(e2)

    def _send_text_alert(self, name, timestamp):
        self._send_text(f"<b>Внимание - АЗС Мониторинг</b>\n\n<b>Зона:</b> {name}\n<b>Время:</b> {timestamp}\nОбнаружено движение в зоне")

    def _send_text(self, text):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        requests.post(url, json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}, timeout=10).raise_for_status()

    def _send_photo(self, caption, frame):
        success, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            raise ValueError("Не удалось закодировать кадр")
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        files = {"photo": ("alert.jpg", buf.tobytes(), "image/jpeg")}
        requests.post(url, data={"chat_id": self.chat_id, "caption": caption}, files=files, timeout=15).raise_for_status()