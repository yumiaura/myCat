import configparser
import logging
from pathlib import Path

from PySide6 import QtWidgets

from . import i18n, menu_config, speech_bubble

logger = logging.getLogger(__name__)
tr = i18n.tr

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, config_path: Path = None, main_window=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.config_path = config_path
        self.main_window = main_window
        self.setMinimumWidth(300)

        # Setup UI
        layout = QtWidgets.QVBoxLayout(self)

        # Wait Time
        wait_layout = QtWidgets.QHBoxLayout()
        wait_label = QtWidgets.QLabel(tr("Animation Wait Time (s):"))
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

        # The "Reminder" toggle: on (default) flies a banner plane across the
        # screen; off makes the cat speak every message in a bubble above its
        # head instead — no plane.
        self.reminder_checkbox = QtWidgets.QCheckBox(tr("Reminder"))
        self.reminder_checkbox.setToolTip(
            tr("On: messages fly across the screen. Off: the cat says them in a speech bubble.")
        )
        self.reminder_checkbox.setChecked(speech_bubble.reminder_flyby_enabled(self.config_path))
        layout.addWidget(self.reminder_checkbox)

        # Which feature entries show in the right-click / tray menu.
        menu_group = QtWidgets.QGroupBox(tr("Show in menu"))
        menu_group_layout = QtWidgets.QVBoxLayout(menu_group)
        visible = menu_config.load_menu_visibility(self.config_path)
        self.menu_checkboxes = {}
        for key, label in menu_config.MENU_ITEMS:
            checkbox = QtWidgets.QCheckBox(tr(label))
            checkbox.setChecked(visible.get(key, True))
            self.menu_checkboxes[key] = checkbox
            menu_group_layout.addWidget(checkbox)
        layout.addWidget(menu_group)

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
                QtWidgets.QMessageBox.critical(self, tr("Error"), f"{tr('Failed to save settings:')}\n{e}")

        # Persist which feature entries appear in the cat / tray menus.
        try:
            menu_config.save_menu_visibility(
                {key: box.isChecked() for key, box in self.menu_checkboxes.items()},
                self.config_path,
            )
        except Exception as e:
            logger.error(f"Error saving menu visibility: {e}")

        try:
            speech_bubble.set_reminder_flyby(self.reminder_checkbox.isChecked(), self.config_path)
        except Exception as e:
            logger.error(f"Error saving Reminder setting: {e}")

        super().accept()
