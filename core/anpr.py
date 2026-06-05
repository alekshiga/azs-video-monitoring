import os
import re
import time
import threading

import cv2
import numpy as np

# Папка для отладочных снимков распознанных/обработанных номеров
ANPR_DEBUG_DIR = "incidents/anpr_debug"

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
    if not RU_PLATE_RE.match(plate):
        return False
    region = plate[6:]
    if len(region) == 3 and region[0] not in "179":
        return False
    return True


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


    def _ocr_candidates(self, image):
        try:
            results = self._reader.readtext(image)
        except Exception as e:
            print(f"[ANPR] Ошибка OCR: {e}")
            return []

        frags = []
        for _, text, conf in results:
            norm = normalize_plate(text)
            if not norm or norm == "RUS" or len(norm) > 9:
                continue
            frags.append((norm, float(conf)))

        candidates = list(frags)
        for i in range(len(frags) - 1):           # склейка соседних (основа+регион)
            a, ca = frags[i]
            b, cb = frags[i + 1]
            candidates.append((a + b, min(ca, cb)))
        if frags:                                  # полная склейка
            candidates.append(("".join(f for f, _ in frags),
                               min(c for _, c in frags)))
        return candidates

    def recognize_from_crop(self, plate_crop):
        if not self._ensure_reader() or plate_crop is None or plate_crop.size == 0:
            return None, 0.0
        best_plate, best_conf = None, 0.0
        for text, conf in self._ocr_candidates(plate_crop):
            norm = normalize_plate(text)
            for variant in (norm, fix_ocr_confusions(norm)):
                if is_valid_ru_plate(variant) and conf > best_conf:
                    best_plate, best_conf = variant, float(conf)
        return best_plate, best_conf

    def recognize_best(self, region, debug_tag=None):
        if not self._ensure_reader() or region is None or region.size == 0:
            return None, 0.0, None

        variants = self._make_variants(region)
        best_plate, best_conf, best_img = None, 0.0, None
        for name, img in variants:
            for text, conf in self._ocr_candidates(img):
                norm = normalize_plate(text)
                for variant in (norm, fix_ocr_confusions(norm)):
                    if is_valid_ru_plate(variant) and conf > best_conf:
                        best_plate, best_conf, best_img = variant, float(conf), img

        if debug_tag is not None and best_plate:
            self._save_debug(region, best_img, best_plate, best_conf, debug_tag)
        return best_plate, best_conf, best_img

    @staticmethod
    def _order_points(pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]      # top-left
        rect[2] = pts[np.argmax(s)]      # bottom-right
        d = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(d)]      # top-right
        rect[3] = pts[np.argmax(d)]      # bottom-left
        return rect

    def _deskew_plate(self, gray):
        try:
            h, w = gray.shape[:2]
            # сглаживание + поиск краёв
            blur = cv2.bilateralFilter(gray, 11, 17, 17)
            edges = cv2.Canny(blur, 30, 200)
            edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
            cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:12]
            for c in cnts:
                area = cv2.contourArea(c)
                if area < (w * h) * 0.02:
                    continue
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                if len(approx) != 4:
                    continue
                pts = approx.reshape(4, 2).astype("float32")
                rect = self._order_points(pts)
                (tl, tr, br, bl) = rect
                wA = np.linalg.norm(br - bl); wB = np.linalg.norm(tr - tl)
                hA = np.linalg.norm(tr - br); hB = np.linalg.norm(tl - bl)
                pw, ph = int(max(wA, wB)), int(max(hA, hB))
                if pw < 40 or ph < 12:
                    continue
                ar = pw / float(ph)
                if ar < 2.0 or ar > 7.0:
                    continue
                dst = np.array([[0, 0], [pw - 1, 0], [pw - 1, ph - 1], [0, ph - 1]],
                               dtype="float32")
                M = cv2.getPerspectiveTransform(rect, dst)
                return cv2.warpPerspective(gray, M, (pw, ph))
        except Exception:
            pass
        return None

    def _make_variants(self, region):
        variants = []
        try:
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        except Exception:
            gray = region

        # 0) попытка выпрямить перспективу и работать с самой табличкой
        plate = self._deskew_plate(gray)
        base_imgs = []
        if plate is not None:
            base_imgs.append(("plate", plate))
        base_imgs.append(("full", gray))

        for tag, g in base_imgs:
            h, w = g.shape[:2]
            # апскейл до читаемого размера
            target_w = 600
            if w < target_w:
                sc = target_w / max(w, 1)
                g = cv2.resize(g, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)

            # шумоподавление
            den = cv2.fastNlMeansDenoising(g, None, h=10, templateWindowSize=7,
                                           searchWindowSize=21)
            # контраст (CLAHE)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            cl = clahe.apply(den)
            # резкость (unsharp mask)
            blur = cv2.GaussianBlur(cl, (0, 0), 3)
            sharp = cv2.addWeighted(cl, 1.6, blur, -0.6, 0)

            def to_bgr(x):
                return cv2.cvtColor(x, cv2.COLOR_GRAY2BGR)

            variants.append((f"{tag}_sharp", to_bgr(sharp)))
            variants.append((f"{tag}_clahe", to_bgr(cl)))
            # бинаризация Оцу
            _, otsu = cv2.threshold(sharp, 0, 255,
                                    cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append((f"{tag}_otsu", to_bgr(otsu)))
            # адаптивная бинаризация
            adap = cv2.adaptiveThreshold(sharp, 255,
                                         cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                         cv2.THRESH_BINARY, 25, 9)
            variants.append((f"{tag}_adapt", to_bgr(adap)))
        return variants

    def _save_debug(self, region, best_img, plate, conf, tag):
        try:
            os.makedirs(ANPR_DEBUG_DIR, exist_ok=True)
            from datetime import datetime
            ts = datetime.now().strftime("%H%M%S_%f")[:-3]
            base = os.path.join(ANPR_DEBUG_DIR, f"{tag}_{plate}_{ts}")
            cv2.imwrite(base + "_src.jpg", region)
            if best_img is not None:
                cv2.imwrite(base + "_proc.jpg", best_img)
            print(f"[ANPR debug] {plate} ({conf:.0%}) -> {base}_*.jpg")
        except Exception as e:
            print(f"[ANPR] debug save error: {e}")

    def process_vehicle(self, frame, bbox, track_id, current_time=None, debug=False):
        if track_id is None or not self._ensure_reader():
            return None
        current_time = current_time or time.time()

        last = self._last_try.get(track_id, 0)
        if current_time - last < self.recognize_interval:
            return self._best_by_track.get(track_id)
        self._last_try[track_id] = current_time

        x, y, w, h = bbox
        pad = int(w * 0.05)
        y1 = max(0, y + int(h * 0.40))
        y2 = min(frame.shape[0], y + h)
        x1 = max(0, x - pad)
        x2 = min(frame.shape[1], x + w + pad)
        region = frame[y1:y2, x1:x2]
        if region is None or region.size == 0:
            return self._best_by_track.get(track_id)

        debug_tag = f"trk{track_id}" if debug else None
        plate, conf, _ = self.recognize_best(region, debug_tag=debug_tag)
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
