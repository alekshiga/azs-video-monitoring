import os
import sys
import time

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                      "rtsp_transport;tcp|stimeout;5000000")

import cv2


def main():
    if len(sys.argv) < 2:
        print("Использование: python tools/test_stream.py <URL потока>")
        print("Пример:        python tools/test_stream.py rtsp://10.12.174.77:8554/live/phone")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Подключение к: {url}")
    print("Открытие может занять несколько секунд...")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("\n[ОШИБКА] Не удалось открыть поток. Проверьте:")
        print("  - телефон и ПК в одной Wi-Fi сети;")
        print("  - трансляция в PRISM запущена (в окне MediaMTX видно подключение);")
        print("  - URL и порт скопированы точно;")
        print("  - брандмауэр/файрвол не блокирует подключение.")
        sys.exit(2)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[OK] Поток открыт: {w}x{h}, заявленный FPS: {fps:.1f}")
    print("Окно с видео откроется. Выход - клавиша Q.")

    frames, t0 = 0, time.time()
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[WARN] Кадр не получен (обрыв потока?)")
                break
            frames += 1
            if frames % 30 == 0:
                real_fps = frames / (time.time() - t0)
                print(f"  получено кадров: {frames}, реальный FPS: {real_fps:.1f}")
            cv2.imshow("Test stream (Q - vyhod)", frame)
            if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Завершено.")


if __name__ == "__main__":
    main()
