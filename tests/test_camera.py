import unittest
import cv2

class TestCameraAccess(unittest.TestCase):
    def test_camera_index_0_available(self):
        print("\n[TEST] Проверка камеры с индексом 0...")

        cap = cv2.VideoCapture(0)

        self.assertIsNotNone(cap, "cv2.VideoCapture вернул None")

        is_opened = cap.isOpened()
        self.assertTrue(is_opened, "Камера с индексом 0 не открылась")

        if is_opened:
            print("Камера открыта")
            cap.release()
        else:
            print("Камера не открылась")

    def test_camera_can_read_frame(self):
        print("\n[TEST] Проверка чтения кадра с камеры 0...")

        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            self.skipTest("Камера не открылась")

        ret, frame = cap.read()

        self.assertTrue(ret, "Не удалось прочитать кадр с камеры")
        self.assertIsNotNone(frame, "Кадр равен None")

        if frame is not None:
            height, width = frame.shape[:2]
            print(f"  Размер кадра: {width}x{height}")
            self.assertGreater(width, 0, "Ширина кадра = 0")
            self.assertGreater(height, 0, "Высота кадра = 0")

        cap.release()
        print("Чтение кадра успешно")