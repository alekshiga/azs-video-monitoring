import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

smtp_server = "smtp.yandex.ru"
smtp_port = 465
sender = os.getenv("EMAIL_SENDER", "silyanovser@yandex.ru")
password = os.getenv("EMAIL_PASSWORD", "")
receiver = os.getenv("EMAIL_RECEIVER", "alekshiga@vk.com")
cooldown = int(os.getenv("EMAIL_COOLDOWN", 30))
last_sent = {}

msg = MIMEText("Тестовое письмо из Python")
msg["Subject"] = "Тест"
msg["From"] = sender
msg["To"] = receiver

try:
    with smtplib.SMTP_SSL("smtp.yandex.ru", 465) as server:
        server.login(sender, password)
        server.send_message(msg)
        print("Письмо отправлено")
except Exception as e:
    print(f"Ошибка: {e}")