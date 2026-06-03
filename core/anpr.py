import re
import time
import threading

RU_PLATE_LETTERS = "ABEKMHOPCTYX"  # допустимые буквы латиница, как их видит OCR
CYR_TO_LAT = {
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
    "О": "O", "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",
}

# Шаблон российского автомобильного номера буква, 3 цифры, 2 буквы, 2-3 цифры региона

RU_PLATE_RE = re.compile(
    r"^[" + RU_PLATE_LETTERS + r"]\d{3}[" + RU_PLATE_LETTERS + r"]{2}\d{2,3}$"
)


def normalize_plate(text: str) -> str:
    """Приводит распознанную строку к виду номера РФ"""
    if not text:
        return ""
    t = text.upper().strip()
    # заменяем кириллицу на латиницу, убираем всё кроме букв/цифр
    out = []
    for ch in t:
        ch = CYR_TO_LAT.get(ch, ch)
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def is_valid_ru_plate(plate: str) -> bool:
    """
    Проверяет соответствие строки формату номера РФ
    """
    return bool(RU_PLATE_RE.match(plate))


class PlateRecognizer:
    def __init__(self, languages=None, gpu=True, recognize_interval=1.5,
                 min_confidence=0.4):
        self.languages = languages or ["en"]  # номера РФ читаем латиницей
        self.gpu = gpu
        self.recognize_interval = recognize_interval
        self.min_confidence = min_confidence

        self._reader = None
        self._reader_lock = threading.Lock()
        self._available = None  # None если ещё не проверяли, True/False по итогу

        self._best_by_track = {}
        self._last_try = {}

    def _ensure_reader(self):
        if self._available is not None:
            return self._available
        with self._reader_lock:
            if self._available is not None:
                return self._available
            try:
                import easyocr
                self._reader = easyocr.Reader(self.languages, gpu=self.gpu,
                                              verbose=False)
                self._available = True
                print("[ANPR] OCR-движок EasyOCR загружен")
            except Exception as e:
                self._available = False
                print("[ANPR] OCR недоступен, распознавание номеров не работает:",
                      repr(str(e))[:200])
        return self._available

    @property
    def available(self) -> bool:
        return self._ensure_reader()


    def recognize_from_crop(self, plate_crop):
        """
        Распознает номер на готовом изображении
        """
        if not self._ensure_reader() or plate_crop is None or plate_crop.size == 0:
            return None, 0.0
        try:
            results = self._reader.readtext(plate_crop)
        except Exception as e:
            print(f"[ANPR] Ошибка OCR: {e}")
            return None, 0.0

        best_plate, best_conf = None, 0.0
        for _, text, conf in results:
            norm = normalize_plate(text)
            if is_valid_ru_plate(norm) and conf > best_conf:
                best_plate, best_conf = norm, float(conf)
        return best_plate, best_conf

    def process_vehicle(self, frame, bbox, track_id, current_time=None):
        """
        Пытается распознать номер у транспортного средства с троттлингом
        В контексте систем оптического распознавания текста (OCR) троттлинг (throttling)
        означает искусственное ограничение скорости обработки документов или количества запросов в секунду.
        """
        if track_id is None or not self._ensure_reader():
            return None
        current_time = current_time or time.time()

        last = self._last_try.get(track_id, 0)
        if current_time - last < self.recognize_interval:
            return self._best_by_track.get(track_id)
        self._last_try[track_id] = current_time

        x, y, w, h = bbox
        y1 = max(0, y + int(h * 0.45))
        y2 = max(0, y + h)
        x1 = max(0, x)
        x2 = max(0, x + w)
        crop = frame[y1:y2, x1:x2]
        if crop is None or crop.size == 0:
            return self._best_by_track.get(track_id)

        plate, conf = self.recognize_from_crop(crop)
        if plate and conf >= self.min_confidence:
            prev = self._best_by_track.get(track_id)
            if prev is None or conf > prev["conf"]:
                self._best_by_track[track_id] = {
                    "plate": plate, "conf": conf, "ts": current_time
                }
        return self._best_by_track.get(track_id)

    def get_best(self, track_id):
        return self._best_by_track.get(track_id)

    def cleanup(self, active_track_ids):
        """
        Удаляет данные по трекам, которых больше нет в кадре
        """
        for tid in list(self._best_by_track):
            if tid not in active_track_ids:
                self._best_by_track.pop(tid, None)
                self._last_try.pop(tid, None)
