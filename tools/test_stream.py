import os
import sys
import time

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                      "rtsp_transport;tcp|stimeout;5000000")

import cv2
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel


class StreamViewer(QLabel):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.cap = None
        self.setWindowTitle("Проверка потока (Q — выход)")
        self.setMinimumSize(640, 480)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#202020; color:#dddddd; font-size:16px;")
        self.setText("Подключение...")

        print(f"Подключение к: {url}")
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            print("\n[ОШИБКА] Не удалось открыть поток. Проверьте:")
            print("  - телефон и ПК в одной Wi-Fi сети;")
            print("  - трансляция в PRISM запущена (в окне MediaMTX видно подключение);")
            print("  - URL и порт скопированы точно.")
            self.setText("Не удалось открыть поток (см. консоль)")
            return
        self.cap = cap

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"[OK] Поток открыт: {w}x{h}, заявленный FPS: {fps:.1f}")
        print("Окно с видео открыто. Выход — клавиша Q.")

        self.frames = 0
        self.t0 = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(30)

    def _tick(self):
        if not self.cap:
            return
        ret, frame = self.cap.read()
        if not ret or frame is None:
            print("[WARN] Кадр не получен (обрыв потока?)")
            return
        self.frames += 1
        if self.frames % 30 == 0:
            real = self.frames / (time.time() - self.t0)
            print(f"  получено кадров: {self.frames}, реальный FPS: {real:.1f}")

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        hh, ww, ch = rgb.shape
        img = QImage(rgb.tobytes(), ww, hh, ch * ww, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pix)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.close()

    def closeEvent(self, event):
        if self.cap:
            self.cap.release()
        print("Завершено.")
        event.accept()


def main():
    if len(sys.argv) < 2:
        print("Использование: python tools/test_stream.py <URL потока>")
        print("Пример:        python tools/test_stream.py rtsp://10.12.174.77:8554/live/phone")
        sys.exit(1)

    app = QApplication(sys.argv)
    viewer = StreamViewer(sys.argv[1])
    viewer.resize(720, 960)
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
