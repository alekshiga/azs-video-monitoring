import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from input.source_manager import SourceManager
from input.video_thread import VideoThread
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    font = QFont("Segue UI", 10)
    app.setFont(font)

    source_manager = SourceManager()
    video_thread = VideoThread(source_manager)

    window = MainWindow(video_thread, source_manager)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
