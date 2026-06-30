import configparser
import logging
from pathlib import Path

from PySide6 import QtWidgets

logger = logging.getLogger(__name__)

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, config_path: Path = None, main_window=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config_path = config_path
        self.main_window = main_window
        self.setMinimumWidth(300)

        # Setup UI
        layout = QtWidgets.QVBoxLayout(self)

        # Wait Time
        wait_layout = QtWidgets.QHBoxLayout()
        wait_label = QtWidgets.QLabel("Animation Wait Time (s):")
        self.wait_spinbox = QtWidgets.QDoubleSpinBox()
        self.wait_spinbox.setRange(0.5, 60.0)
        self.wait_spinbox.setSingleStep(0.5)
        
        # Load current wait time from main window if available, else default to 5.0
        current_wait = 5.0
        if self.main_window and hasattr(self.main_window, 'wait_time'):
            current_wait = self.main_window.wait_time
        self.wait_spinbox.setValue(current_wait)

        wait_layout.addWidget(wait_label)
        wait_layout.addWidget(self.wait_spinbox)
        layout.addLayout(wait_layout)

        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self):
        # Save settings
        if self.config_path:
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                config = configparser.ConfigParser()
                if self.config_path.exists():
                    config.read(self.config_path)
                
                if 'settings' not in config:
                    config.add_section('settings')
                
                new_wait_time = self.wait_spinbox.value()
                config['settings']['wait_time'] = str(new_wait_time)
                
                with open(self.config_path, 'w') as f:
                    config.write(f)
                
                logger.info(f"Saved wait_time setting to INI: {new_wait_time}")

                # Apply to main window immediately
                if self.main_window:
                    self.main_window.wait_time = new_wait_time

            except Exception as e:
                logger.error(f"Error saving settings to INI file: {e}")
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")

        super().accept()
