import smtplib
import threading
import time
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from dotenv import load_dotenv
import cv2

from app_paths import env_file

load_dotenv(env_file())


class EmailNotifier:
    def __init__(self):
        self.smtp_server = "smtp.yandex.ru"
        self.smtp_port = 465
        self.sender = os.getenv("EMAIL_SENDER", "silyanovser@yandex.ru")
        self.password = os.getenv("EMAIL_PASSWORD", "")
        self.receiver = os.getenv("EMAIL_RECEIVER", "alekshiga@vk.com")
        self.cooldown = int(os.getenv("EMAIL_COOLDOWN", 30))
        self.last_sent = {}

    def _clean_text(self, text, default="unknown"):
        if not text:
            return default
        cleaned = re.sub(r'[^a-zA-Z0-9\s\-]', '', str(text))
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned if cleaned else default

    def send_alert(self, zone_name, class_name, time_in_zone, frame=None):
        if not self.sender or not self.password or not self.receiver:
            print("[Email] Ошибка: не настроены переменные в .env")
            return

        key = (zone_name, class_name)
        now = time.time()
        if now - self.last_sent.get(key, 0) < self.cooldown:
            return

        self.last_sent[key] = now

        threading.Thread(
            target=self._send,
            args=(zone_name, class_name, time_in_zone, frame),
            daemon=True
        ).start()

    def _send(self, zone_name, class_name, time_in_zone, frame):
        try:
            clean_zone = self._clean_text(zone_name, "Zone")
            clean_class = self._clean_text(class_name, "Object")

            if frame is not None:
                msg = MIMEMultipart()
                msg["Subject"] = "AZS Alert"
                msg["From"] = self.sender
                msg["To"] = self.receiver

                text = f"Zone: {clean_zone}\nObject: {clean_class}\nTime in zone: {time_in_zone} sec"
                msg.attach(MIMEText(text, "plain", "utf-8"))

                success, buf = cv2.imencode(".jpg", frame)
                if success:
                    image = MIMEImage(buf.tobytes())
                    image.add_header("Content-Disposition", "attachment", filename="alert.jpg")
                    msg.attach(image)
            else:
                msg = MIMEText(f"Zone: {clean_zone}\nObject: {clean_class}\nTime in zone: {time_in_zone} sec", "plain",
                               "utf-8")
                msg["Subject"] = "AZS Alert"
                msg["From"] = self.sender
                msg["To"] = self.receiver

            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.sender, self.password)
                server.send_message(msg)
            print(f"[Email] Sent to {self.receiver}")
        except Exception as e:
            print(f"[Email] Error: {e}")
            import traceback
            traceback.print_exc()