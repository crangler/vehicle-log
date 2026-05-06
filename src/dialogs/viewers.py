import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSlider, QWidget,
)
from PySide6.QtCore import Qt, QEvent, QUrl
from PySide6.QtGui import QPixmap, QIcon, QDesktopServices

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
    _HAS_PDF = True
except ImportError:
    _HAS_PDF = False


# ── image viewer ─────────────────────────────────────────────────────────────

class ImageViewerDialog(QDialog):
    _ZOOM_STEP = 1.25

    def __init__(self, parent, paths: list[str], index: int = 0):
        super().__init__(parent)
        self._paths = paths
        self._index = index
        self._pixmap = QPixmap()
        self._scale = 1.0
        self._fit = True
        self._build_ui()
        self.resize(900, 650)
        self._load_image()

    def _build_ui(self):
        self.setWindowFlags(self.windowFlags() |
                            Qt.WindowType.WindowMaximizeButtonHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._scroll = QScrollArea()
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setWidgetResizable(False)
        self._scroll.viewport().installEventFilter(self)
        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setWidget(self._img_label)
        layout.addWidget(self._scroll)

        bar = QHBoxLayout()
        self._prev_btn = QPushButton("◀ Prev")
        self._prev_btn.clicked.connect(self._prev)
        self._next_btn = QPushButton("Next ▶")
        self._next_btn.clicked.connect(self._next)
        bar.addWidget(self._prev_btn)
        bar.addWidget(self._next_btn)
        bar.addStretch()

        zoom_out = QPushButton("−")
        zoom_out.setFixedWidth(28)
        zoom_out.clicked.connect(self._zoom_out)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(52)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_in = QPushButton("+")
        zoom_in.setFixedWidth(28)
        zoom_in.clicked.connect(self._zoom_in)
        self._fit_btn = QPushButton("Fit")
        self._fit_btn.setCheckable(True)
        self._fit_btn.setChecked(True)
        self._fit_btn.clicked.connect(self._toggle_fit)

        bar.addWidget(zoom_out)
        bar.addWidget(self._zoom_label)
        bar.addWidget(zoom_in)
        bar.addWidget(self._fit_btn)
        layout.addLayout(bar)

    def _load_image(self):
        if not self._paths:
            return
        self._pixmap = QPixmap(self._paths[self._index])
        name = os.path.basename(self._paths[self._index])
        self.setWindowTitle(
            f"{name}  ({self._index + 1} of {len(self._paths)})")
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < len(self._paths) - 1)
        self._apply_display()

    def _apply_display(self):
        if self._pixmap.isNull():
            self._img_label.setText("(Image not found)")
            return
        if self._fit:
            scaled = self._pixmap.scaled(
                self._scroll.viewport().size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._scale = scaled.width() / self._pixmap.width()
        else:
            scaled = self._pixmap.scaled(
                round(self._pixmap.width() * self._scale),
                round(self._pixmap.height() * self._scale),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._img_label.setPixmap(scaled)
        self._img_label.resize(scaled.size())
        self._zoom_label.setText(f"{round(self._scale * 100)}%")

    def _toggle_fit(self, checked: bool):
        self._fit = checked
        self._fit_btn.setChecked(checked)
        self._apply_display()

    def _zoom_in(self):
        self._set_zoom(self._scale * self._ZOOM_STEP)

    def _zoom_out(self):
        self._set_zoom(self._scale / self._ZOOM_STEP)

    def _set_zoom(self, factor: float):
        self._fit = False
        self._fit_btn.setChecked(False)
        self._scale = max(0.05, min(factor, 10.0))
        self._apply_display()

    def _prev(self):
        if self._index > 0:
            self._index -= 1
            self._load_image()

    def _next(self):
        if self._index < len(self._paths) - 1:
            self._index += 1
            self._load_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self._apply_display()

    def eventFilter(self, source, event):
        if source is self._scroll.viewport() and event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.angleDelta().y() > 0:
                    self._zoom_in()
                else:
                    self._zoom_out()
                return True
        return super().eventFilter(source, event)

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_Left:
            self._prev()
        elif k == Qt.Key.Key_Right:
            self._next()
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_in()
        elif k == Qt.Key.Key_Minus:
            self._zoom_out()
        elif k == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._toggle_fit(True)
        elif k == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


# ── video viewer dialog ───────────────────────────────────────────────────────

class VideoViewerDialog(QDialog):
    def __init__(self, parent, path: str):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(path))
        self.setWindowFlags(self.windowFlags() |
                            Qt.WindowType.WindowMaximizeButtonHint)
        self._path = path
        self._build_ui()
        self.resize(860, 560)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._video_widget = QVideoWidget()
        layout.addWidget(self._video_widget)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video_widget)
        self._player.setSource(QUrl.fromLocalFile(self._path))

        controls = QHBoxLayout()

        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setFixedWidth(80)
        self._play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self._play_btn)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._player.setPosition)
        controls.addWidget(self._slider)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setFixedWidth(90)
        self._time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self._time_label)

        layout.addLayout(controls)

        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.play()

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.setText("⏸ Pause" if playing else "▶ Play")

    def _on_duration_changed(self, duration: int):
        self._slider.setRange(0, duration)
        self._update_time()

    def _on_position_changed(self, position: int):
        if not self._slider.isSliderDown():
            self._slider.setValue(position)
        self._update_time()

    def _update_time(self):
        self._time_label.setText(
            f"{self._fmt_ms(self._player.position())} / {self._fmt_ms(self._player.duration())}"
        )

    def closeEvent(self, event):
        self._player.stop()
        super().closeEvent(event)


# ── pdf viewer dialog ─────────────────────────────────────────────────────────

class PdfViewerDialog(QDialog):
    _ZOOM_STEP = 1.25

    def __init__(self, parent, path: str):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(path))
        self.setWindowFlags(self.windowFlags() |
                            Qt.WindowType.WindowMaximizeButtonHint)
        self._zoom = 1.0
        self._build_ui(path)
        self.resize(800, 960)

    def _build_ui(self, path: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._doc = QPdfDocument(self)
        self._doc.load(path)

        self._view = QPdfView(self)
        self._view.setDocument(self._doc)
        self._view.setPageMode(QPdfView.PageMode.MultiPage)
        self._view.setZoomMode(QPdfView.ZoomMode.Custom)
        self._view.setZoomFactor(self._zoom)
        layout.addWidget(self._view)

        bar = QHBoxLayout()
        bar.addStretch()
        zoom_out = QPushButton("−")
        zoom_out.setFixedWidth(28)
        zoom_out.clicked.connect(self._zoom_out)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(52)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_in = QPushButton("+")
        zoom_in.setFixedWidth(28)
        zoom_in.clicked.connect(self._zoom_in)
        bar.addWidget(zoom_out)
        bar.addWidget(self._zoom_label)
        bar.addWidget(zoom_in)
        layout.addLayout(bar)

    def _zoom_in(self):
        self._set_zoom(self._zoom * self._ZOOM_STEP)

    def _zoom_out(self):
        self._set_zoom(self._zoom / self._ZOOM_STEP)

    def _set_zoom(self, factor: float):
        self._zoom = max(0.1, min(factor, 5.0))
        self._view.setZoomFactor(self._zoom)
        self._zoom_label.setText(f"{round(self._zoom * 100)}%")


def _open_file(
    parent: QWidget,
    path: str,
    ft: str,
    image_paths: list[str] | None = None,
    img_row: int = 0,
) -> None:
    if ft == "image":
        ImageViewerDialog(parent, image_paths or [path], img_row).exec()
    elif ft == "video":
        if _HAS_MULTIMEDIA:
            VideoViewerDialog(parent, path).exec()
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    elif ft == "pdf":
        if _HAS_PDF:
            PdfViewerDialog(parent, path).exec()
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
