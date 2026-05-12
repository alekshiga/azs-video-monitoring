import os
import threading
import time
from datetime import datetime

import cv2
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_COOLDOWN_SECONDS = 10.0

class TelegramNotifier:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.cooldown = TELEGRAM_COOLDOWN_SECONDS

        self.last_sent_time = {}
        self.enabled = True
        self._lock = threading.Lock()

        self.total_sent = 0
        self.total_errors = 0

    def send_alert(self, zone_index, zone_name=None, frame=None):
        if not self.enabled:
            return False

        with self._lock:
            now = time.time()
            last = self.last_sent_time.get(zone_index, 0)

            if now - last < self.cooldown:
                return False

            self.last_sent_time[zone_index] = now

        thread = threading.Thread(
            target=self._send_alert_impl,
            args=(zone_index, zone_name, frame),
            daemon=True
        )
        thread.start()
        return True

    def _send_alert_impl(self, zone_index, zone_name=None, frame=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = zone_name or f"Зона {zone_index}"

        try:
            if frame is not None:
                # Проверяем что кадр валидный
                if frame.size == 0 or frame.shape[0] == 0 or frame.shape[1] == 0:
                    print(f"[Telegram] ⚠️ Пустой кадр, отправляем текст")
                    self._send_text_alert(name, timestamp)
                    return

                # Добавляем надписи на кадр
                annotated = frame.copy()

                cv2.putText(
                    annotated, timestamp,
                    (10, annotated.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 255), 2
                )
                cv2.putText(
                    annotated, f"ALERT: {name}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 0, 255), 2
                )

                h, w = annotated.shape[:2]
                if w > 1920 or h > 1080:
                    scale = min(1920 / w, 1080 / h)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    annotated = cv2.resize(annotated, (new_w, new_h))

                caption = (
                    f"Внимание\n"
                    f"Зона: {name}\n"
                    f"Время: {timestamp}\n"
                    f"Движение в запретной зоне"
                )

                self._send_photo(caption, annotated)
            else:
                self._send_text_alert(name, timestamp)

            self.total_sent += 1
            print(f"[Telegram] Отправлено: {name} (всего: {self.total_sent})")

        except Exception as e:
            self.total_errors += 1
            print(f"[Telegram] Ошибка: {e}")

            try:
                self._send_text_alert(name, timestamp)
                self.total_sent += 1
                print(f"[Telegram] Отправлено (текст)")
            except Exception as e2:
                print(e2)

    def _send_text_alert(self, name, timestamp):
        """Отправка текстового сообщения"""
        text = (
            f"<b>Внимание - АЗС Мониторинг</b>\n\n"
            f"<b>Зона:</b> {name}\n"
            f"<b>Время:</b> {timestamp}\n"
            f"Обнаружено движение в отслеживаемой зоне"
        )
        self._send_text(text)

    def _send_text(self, text):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=10)

        if not response.ok:
            error_info = response.json() if response.headers.get(
                'content-type', ''
            ).startswith('application/json') else response.text
            print(f"[Telegram] Ответ API: {error_info}")

        response.raise_for_status()

    def _send_photo(self, caption, frame):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"

        # Кодируем в JPEG
        success, buffer = cv2.imencode(
            '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
        )

        if not success:
            raise ValueError("Не удалось закодировать кадр в JPEG")

        photo_bytes = buffer.tobytes()

        size_mb = len(photo_bytes) / (1024 * 1024)
        if size_mb > 9:
            success, buffer = cv2.imencode(
                '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50]
            )
            if not success:
                raise ValueError("Не удалось сжать кадр")
            photo_bytes = buffer.tobytes()
            print(f"[Telegram] Фото сжато: {size_mb:.1f}MB → "
                  f"{len(photo_bytes) / (1024 * 1024):.1f}MB")

        if len(caption) > 1024:
            caption = caption[:1020] + "..."

        files = {
            "photo": ("alert.jpg", photo_bytes, "image/jpeg")
        }
        data = {
            "chat_id": self.chat_id,
            "caption": caption,
        }

        response = requests.post(url, data=data, files=files, timeout=15)

        if not response.ok:
            # Логируем подробную ошибку от Telegram API
            try:
                error_info = response.json()
                print(f"[Telegram] API ответ: {error_info}")
            except Exception:
                print(f"[Telegram] Ответ: {response.text}")

        response.raise_for_status()
