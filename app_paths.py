"""
Единая точка разрешения путей для приложения

Логика:
- В режиме разработки запуск main.py и ресурсы, и изменяемые данные
  лежат в корне проекта и поведение полностью совпадает с прежним
- В собранном виде (PyInstaller, sys.frozen):
    * ресурсы только для чтения (модель, шаблоны конфигов, tools) берутся из
      папки программы (sys._MEIPASS) resource_path();
    * изменяемые данные (config рабочие, БД, инциденты, .env) пишутся в
      %LOCALAPPDATA%\\AZS-Monitoring user_data_path().
"""

import os
import sys
import shutil

APP_NAME = "AZS-Monitoring"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_root() -> str:
    """Корень для ресурсов только для чтения"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*rel: str) -> str:
    """Путь к встроенному ресурсу только для чтения"""
    return os.path.join(_bundle_root(), *rel)


def user_data_root() -> str:
    """Корень для изменяемых пользовательских данных"""
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    # dev: пишем в корень проекта, как и раньше
    return os.path.dirname(os.path.abspath(__file__))


def user_data_path(*rel: str) -> str:
    """Путь к изменяемому файлу/папке в пользовательской директории"""
    return os.path.join(user_data_root(), *rel)


def env_file() -> str:
    """Путь к .env (читается нотификаторами)"""
    return user_data_path(".env")


def archive_root() -> str:
    """Корень видеоархива (сегменты записи), изменяемые данные"""
    return user_data_path("archive")


def ensure_user_data() -> None:
    """
    Первый запуск собранного приложения: создаёт изменяемые папки и
    переносит дефолтные конфиги/шаблон .env в пользовательскую директорию
    В режиме разработки ничего не делает
    """
    if not is_frozen():
        return

    root = user_data_root()
    for sub in ("", "config", "data", "incidents", os.path.join("incidents", "anpr_debug"), "archive"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    # Перенос дефолтных конфигов, если их еще нет у пользователя
    src_cfg = resource_path("config")
    dst_cfg = os.path.join(root, "config")
    if os.path.isdir(src_cfg):
        for name in os.listdir(src_cfg):
            s = os.path.join(src_cfg, name)
            d = os.path.join(dst_cfg, name)
            if os.path.isfile(s) and not os.path.exists(d):
                try:
                    shutil.copy2(s, d)
                except OSError:
                    pass

    # Шаблон .env, если пользователь еще не создал свой
    env_dst = env_file()
    if not os.path.exists(env_dst):
        try:
            with open(env_dst, "w", encoding="utf-8") as f:
                f.write(
                    "# Настройки уведомлений — заполните своими данными\n"
                    "TELEGRAM_BOT_TOKEN=\n"
                    "TELEGRAM_CHAT_ID=\n"
                    "TELEGRAM_COOLDOWN_SECONDS=10.0\n\n"
                    "EMAIL_SENDER=\n"
                    "EMAIL_PASSWORD=\n"
                    "EMAIL_RECEIVER=\n"
                    "EMAIL_SMTP_SERVER=smtp.yandex.ru\n"
                    "EMAIL_SMTP_PORT=465\n"
                    "EMAIL_COOLDOWN=30\n"
                )
        except OSError:
            pass
