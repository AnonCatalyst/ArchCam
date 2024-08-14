import sys
import os
import logging
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QComboBox, QTableWidget, 
    QTableWidgetItem, QHeaderView, QDialog, QLineEdit, QFormLayout, QTabWidget, QTextEdit, QSplitter, 
    QHBoxLayout
)
from PyQt6.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject
from PyQt6.QtGui import QImage, QPixmap, QIcon
import mss
from PIL import Image
import subprocess

# Set up logging
logger = logging.getLogger('ArchCam')
logger.setLevel(logging.DEBUG)

# Console handler for terminal output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# File handler for saving logs to a file
file_handler = logging.FileHandler('archcam.log')
file_handler.setLevel(logging.DEBUG)

# Formatter for log messages
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

class FullScreenshotWindow(QDialog):
    def __init__(self, image):
        super().__init__()
        self.setWindowTitle("Full Screenshot")
        self.setFixedSize(1000, 800)  # Adjusted size for better fit
        self.image_label = QLabel(self)
        pixmap = QPixmap.fromImage(image)
        self.image_label.setPixmap(pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio))
        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        self.setLayout(layout)

class ScreenCaptureTask(QRunnable):
    update_image_signal = pyqtSignal(QImage)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        while self.running:
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Full screen capture
                screenshot = sct.grab(monitor)
                image = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                qt_image = QImage(image.tobytes(), image.width, image.height, image.width * 3, QImage.Format.Format_RGB888)
                self.update_image_signal.emit(qt_image)

    def stop(self):
        self.running = False

class ArchCam(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ArchCam - Screen Capture and Recording")
        self.setFixedSize(1100, 600)  # Increased width for better fit
        self.video_format = "mp4"
        self.ffmpeg_options = []
        self.recorder_process = None
        self.thread_pool = QThreadPool()
        self.screenshot_count = 1
        self.recording_count = 1
        self.screenshot_format = "png"
        
        # Ensure directories exist
        self.ensure_directories()

        # Set up tabs
        self.tabs = QTabWidget()
        self.create_widgets()
        self.setup_logging_tab()

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

    def create_widgets(self):
        # Control layout
        self.control_layout = QVBoxLayout()
        self.control_layout.setSpacing(10)

        # Splitter for separating screenshots and recordings
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setSizes([600, 600])  # Adjust splitter sizes for better fit

        # Screenshot options
        self.screenshot_layout = QVBoxLayout()
        self.capture_button = QPushButton(QIcon.fromTheme("camera"), "Capture Full Screen")
        self.capture_button.clicked.connect(self.capture_screenshot)
        self.screenshot_layout.addWidget(self.capture_button)

        self.format_selector = QComboBox()
        self.format_selector.addItems(["png", "jpg", "bmp"])
        self.format_selector.setCurrentText("png")
        self.format_selector.currentTextChanged.connect(self.set_screenshot_format)
        self.screenshot_layout.addWidget(self.format_selector)

        # Table with Filename, Details, and Directory columns
        self.screenshot_table = QTableWidget()
        self.screenshot_table.setColumnCount(3)
        self.screenshot_table.setHorizontalHeaderLabels(["Filename", "Details", "Directory"])
        self.screenshot_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.screenshot_table.setStyleSheet("QHeaderView::section { background-color: #4CAF50; color: white; }")
        self.screenshot_table.cellClicked.connect(self.show_full_screenshot)
        self.screenshot_layout.addWidget(self.screenshot_table)

        # Recording options
        self.recording_layout = QVBoxLayout()
        self.start_recording_button = QPushButton(QIcon.fromTheme("media-record"), "Start Recording")
        self.start_recording_button.clicked.connect(self.start_recording)
        self.recording_layout.addWidget(self.start_recording_button)

        self.stop_recording_button = QPushButton(QIcon.fromTheme("media-stop"), "Stop Recording")
        self.stop_recording_button.clicked.connect(self.stop_recording)
        self.recording_layout.addWidget(self.stop_recording_button)

        # Table with Filename, Details, and Directory columns
        self.recording_table = QTableWidget()
        self.recording_table.setColumnCount(3)
        self.recording_table.setHorizontalHeaderLabels(["Filename", "Details", "Directory"])
        self.recording_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.recording_table.setStyleSheet("QHeaderView::section { background-color: #4CAF50; color: white; }")
        self.recording_table.cellClicked.connect(self.show_full_recording)
        self.recording_layout.addWidget(self.recording_table)

        # Add layouts to splitter
        self.screenshot_widget = QWidget()
        self.screenshot_widget.setLayout(self.screenshot_layout)
        self.recording_widget = QWidget()
        self.recording_widget.setLayout(self.recording_layout)
        self.splitter.addWidget(self.screenshot_widget)
        self.splitter.addWidget(self.recording_widget)
        self.control_layout.addWidget(self.splitter)

        # Description and Status box layout
        self.description_status_layout = QHBoxLayout()

        # Description box
        self.description_box = QLabel("ArchCam Features:\n\n"
                                      "- Capture full-screen screenshots.\n"
                                      "- Record screen activities.\n"
                                      "- Save screenshots in various formats.\n"
                                      "- View and manage recorded files.\n"
                                      "- Customizable recording settings.\n"
                                      "- Logging and status updates.")
        self.description_box.setWordWrap(True)  # Allow text to wrap
        self.description_status_layout.addWidget(self.description_box)

        # Status box
        self.status_widget = QWidget()
        self.status_widget.setStyleSheet("background-color: #2e2e2e; border: 1px solid #1e1e1e; padding: 5px;")
        self.status_layout = QVBoxLayout()
        
        self.status_text_edit = QTextEdit()
        self.status_text_edit.setReadOnly(True)
        self.status_text_edit.setStyleSheet("background-color: #2e2e2e; color: #ffffff; border: none;")
        self.status_layout.addWidget(self.status_text_edit)
        
        self.status_widget.setLayout(self.status_layout)
        self.description_status_layout.addWidget(self.status_widget)

        # Add description and status layout
        self.control_layout.addLayout(self.description_status_layout)

        # Add control layout to tabs
        self.control_tab = QWidget()
        self.control_tab.setLayout(self.control_layout)
        self.tabs.addTab(self.control_tab, "Controls")

    def setup_logging_tab(self):
        self.logging_tab = QWidget()
        self.logging_layout = QVBoxLayout()
        self.logging_text_edit = QTextEdit()
        self.logging_text_edit.setReadOnly(True)
        self.logging_layout.addWidget(self.logging_text_edit)
        self.logging_tab.setLayout(self.logging_layout)
        self.tabs.addTab(self.logging_tab, "Logs")

        # Redirect log messages to the QTextEdit widget
        class LogHandler(logging.Handler):
            def __init__(self, text_edit):
                super().__init__()
                self.text_edit = text_edit

            def emit(self, record):
                log_entry = self.format(record)
                self.text_edit.append(log_entry)
                self.text_edit.ensureCursorVisible()

        log_handler = LogHandler(self.logging_text_edit)
        log_handler.setFormatter(formatter)
        logger.addHandler(log_handler)

    def ensure_directories(self):
        if not os.path.exists("Recordings"):
            os.makedirs("Recordings")
        if not os.path.exists("Screenshots"):
            os.makedirs("Screenshots")

    def set_screenshot_format(self, format):
        self.screenshot_format = format

    def capture_screenshot(self):
        monitor = mss.mss().monitors[1]  # Full screen capture
        with mss.mss() as sct:
            screenshot = sct.grab(monitor)

            # Dialog to input filename
            filename_dialog = QDialog(self)
            filename_dialog.setWindowTitle("Save Screenshot")
            filename_dialog.setFixedSize(300, 120)
            layout = QFormLayout()
            filename_input = QLineEdit(filename_dialog)
            filename_input.setText(f"archcam-screenshot{self.screenshot_count}.{self.screenshot_format}")
            layout.addRow(QLabel("Filename:"), filename_input)
            save_button = QPushButton("Save", filename_dialog)
            save_button.clicked.connect(lambda: self.save_screenshot(filename_input.text(), screenshot, filename_dialog))
            layout.addWidget(save_button)
            filename_dialog.setLayout(layout)
            filename_dialog.exec()

    def save_screenshot(self, filename, screenshot, dialog):
        filepath = os.path.join("Screenshots", filename)
        image = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
        image.save(filepath, format=self.screenshot_format)
        logger.info(f"Screenshot saved: {filepath}")
        self.status_text_edit.append(f"Screenshot saved: {filepath}")
        self.screenshot_count += 1
        self.update_screenshot_table()
        dialog.accept()

    def update_screenshot_table(self):
        self.screenshot_table.setRowCount(0)
        for filename in os.listdir("Screenshots"):
            if filename.endswith(f".{self.screenshot_format}"):
                filepath = os.path.join("Screenshots", filename)
                size = os.path.getsize(filepath) / (1024 * 1024)  # Size in MB
                size_str = f"{size:.2f} MB"
                row_position = self.screenshot_table.rowCount()
                self.screenshot_table.insertRow(row_position)
                self.screenshot_table.setItem(row_position, 0, QTableWidgetItem(filename))
                self.screenshot_table.setItem(row_position, 1, QTableWidgetItem(size_str))
                self.screenshot_table.setItem(row_position, 2, QTableWidgetItem(filepath))

    def show_full_screenshot(self, row, column):
        filename = self.screenshot_table.item(row, 0).text()
        filepath = os.path.join("Screenshots", filename)
        image = QImage(filepath)
        full_screenshot_window = FullScreenshotWindow(image)
        full_screenshot_window.exec()

    def start_recording(self):
        if self.recorder_process:
            self.status_text_edit.append("Recording already in progress.")
            return
        filename = f"archcam-recording{self.recording_count}.{self.video_format}"
        self.recorder_process = subprocess.Popen(
            ["ffmpeg", "-f", "x11grab", "-s", "1920x1080", "-i", ":0.0", "-c:v", "libx264", filename],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        logger.info(f"Recording started: {filename}")
        self.status_text_edit.append(f"Recording started: {filename}")

    def stop_recording(self):
        if self.recorder_process:
            self.recorder_process.terminate()
            self.recorder_process.wait()  # Wait for the process to terminate
            self.recorder_process = None
            logger.info("Recording stopped.")
            self.status_text_edit.append("Recording stopped.")

            # Get the last recorded file
            directory = "Recordings"
            files = sorted([f for f in os.listdir(directory) if f.endswith(f".{self.video_format}")])
            if files:
                last_recording = files[-1]
                full_path = os.path.join(directory, last_recording)

                # Get video duration and size
                duration, size = self.get_video_info(full_path)

                # Update status with duration and size
                self.status_text_edit.append(f"Recording saved: {last_recording}")
                self.status_text_edit.append(f"Duration: {duration}")
                self.status_text_edit.append(f"Size: {size}")

                # Update the recording table with the new recording
                self.update_recording_table()

    def get_video_info(self, video_path):
        try:
            # Get video duration and size using ffprobe
            duration_process = subprocess.Popen(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            duration_output, _ = duration_process.communicate()
            duration = float(duration_output.strip())

            size = os.path.getsize(video_path)
            size_mb = size / (1024 * 1024)

            return f"{duration:.2f} seconds", f"{size_mb:.2f} MB"
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return "Unknown", "Unknown"

    def update_recording_table(self):
        self.recording_table.setRowCount(0)
        for filename in os.listdir("Recordings"):
            if filename.endswith(f".{self.video_format}"):
                filepath = os.path.join("Recordings", filename)
                size = os.path.getsize(filepath) / (1024 * 1024)  # Size in MB
                size_str = f"{size:.2f} MB"
                row_position = self.recording_table.rowCount()
                self.recording_table.insertRow(row_position)
                self.recording_table.setItem(row_position, 0, QTableWidgetItem(filename))
                self.recording_table.setItem(row_position, 1, QTableWidgetItem(size_str))
                self.recording_table.setItem(row_position, 2, QTableWidgetItem(filepath))

    def show_full_recording(self, row, column):
        filename = self.recording_table.item(row, 0).text()
        filepath = os.path.join("Recordings", filename)
        # For now, we will just open the file in the default video player
        subprocess.Popen(['xdg-open', filepath], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ArchCam()
    window.show()
    sys.exit(app.exec())
