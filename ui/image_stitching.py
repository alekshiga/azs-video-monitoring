from PyQt6.QtWidgets import QWidget, QGridLayout, QFrame
from ui.video_widget import VideoWidget


class ImageStitcher(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QGridLayout()
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        self.video_widgets = {}
        self.grid_size = (2, 2)

    def set_sources(self, sources):
        count = len(sources)
        if count <= 1:
            self.grid_size = (1, 1)
        elif count <= 4:
            self.grid_size = (2, 2)
        elif count <= 9:
            self.grid_size = (3, 3)
        else:
            self.grid_size = (4, 4)

        self._clear_layout()

        for i, source in enumerate(sources):
            row, col = i // self.grid_size[1], i % self.grid_size[1]
            if source['id'] not in self.video_widgets:
                self.video_widgets[source['id']] = VideoWidget()
            container = QFrame()
            container.setFrameShape(QFrame.Shape.Box)
            container.setStyleSheet("border: 1px solid #cccccc;")
            inner = QGridLayout()
            inner.setContentsMargins(0, 0, 0, 0)
            inner.addWidget(self.video_widgets[source['id']])
            container.setLayout(inner)
            self.layout.addWidget(container, row, col)

        total = self.grid_size[0] * self.grid_size[1]
        for i in range(len(sources), total):
            empty = QFrame()
            empty.setStyleSheet("background-color: black;")
            self.layout.addWidget(empty, i // self.grid_size[1], i % self.grid_size[1])

    def _clear_layout(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def update_frame(self, source_id, frame, active_zones, objects):
        if source_id in self.video_widgets:
            self.video_widgets[source_id].set_frame(frame, active_zones, objects)