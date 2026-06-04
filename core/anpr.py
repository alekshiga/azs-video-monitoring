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
    out = []
    for ch in t:
        ch = CYR_TO_LAT.get(ch, ch)
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1",
             "Z": "2", "B": "8", "S": "5", "G": "6", "T": "7"}
_TO_LETTER = {"0": "O", "1": "I", "8": "B", "5": "S", "6": "G"}


def fix_ocr_confusions(s: str) -> str:
    """
    Позиционная коррекция типичных ошибок OCR для номера РФ формата X000XX22
    """
    if len(s) < 8 or len(s) > 9:
        return s
    mask = "LDDDLL" + "D" * (len(s) - 6)
    out = []
    for ch, m in zip(s, mask):
        if m == "D" and not ch.isdigit():
            ch = _TO_DIGIT.get(ch, ch)
        elif m == "L" and not ch.isalpha():
            ch = _TO_LETTER.get(ch, ch)
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

        frags = []
        for _, text, conf in results:
            norm = normalize_plate(text)
            if not norm or norm == "RUS":
                continue
            if len(norm) > 9:
                continue
            frags.append((norm, float(conf)))

        candidates = []
        for norm, conf in frags:
            candidates.append((norm, conf))
        for i in range(len(frags) - 1):
            a, ca = frags[i]
            b, cb = frags[i + 1]
            candidates.append((a + b, min(ca, cb)))
        if frags:
            candidates.append(("".join(f for f, _ in frags),
                               min(c for _, c in frags)))

        best_plate, best_conf = None, 0.0
        for text, conf in candidates:
            norm = normalize_plate(text)
            for variant in (norm, fix_ocr_confusions(norm)):
                if is_valid_ru_plate(variant) and conf > best_conf:
                    best_plate, best_conf = variant, float(conf)
        return best_plate, best_conf

    def process_vehicle(self, frame, bbox, track_id, current_time=None):
        """
        todo тестовая функция распознавания номера
        """
        if track_id is None or not self._ensure_reader():
            return None
        current_time = current_time or time.time()

        last = self._last_try.get(track_id, 0)
        if current_time - last < self.recognize_interval:
            return self._best_by_track.get(track_id)
        self._last_try[track_id] = current_time

        x, y, w, h = bbox
        y1 = max(0, y + int(h * 0.40))
        y2 = max(0, y + h)
        x1 = max(0, x)
        x2 = max(0, x + w)
        crop = frame[y1:y2, x1:x2]
        if crop is None or crop.size == 0:
            return self._best_by_track.get(track_id)

        crop = self._preprocess(crop)
        plate, conf = self.recognize_from_crop(crop)
        if plate and conf >= self.min_confidence:
            prev = self._best_by_track.get(track_id)
            if prev is None or conf > prev["conf"]:
                self._best_by_track[track_id] = {
                    "plate": plate, "conf": conf, "ts": current_time
                }
        return self._best_by_track.get(track_id)

    @staticmethod
    def _preprocess(crop):
        """
        апскейл маленьких областей и повышение контраста по CLAHE
        """
        try:
            import cv2
            import numpy as np
            h, w = crop.shape[:2]
            # апскейл, если область мелкая (номер должен быть достаточно крупным)
            if w < 400:
                scale = 400.0 / max(w, 1)
                crop = cv2.resize(crop, None, fx=scale, fy=scale,
                                  interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        except Exception:
            return crop

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
