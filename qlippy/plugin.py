"""QGIS plugin entry point."""

import os

from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QIcon

from .assistant import Assistant
from .compat import QAction
from .rules import RuleEngine
from .settings import Settings
from .settings_dialog import SettingsDialog

MENU = "&Qlippy"


class QlippyPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.settings = Settings()
        self.assistant = None
        self.rules = None
        self.actions = []
        self._started = False

    def initGui(self):
        main_window = self.iface.mainWindow()
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))

        self.toggle_action = QAction(icon, "Qlippy", main_window)
        self.toggle_action.setCheckable(True)
        self.toggle_action.setChecked(self.settings.visible)
        self.toggle_action.setToolTip("Show or hide Qlippy")
        self.toggle_action.toggled.connect(self._on_toggle)
        self.iface.addToolBarIcon(self.toggle_action)
        self.iface.addPluginToMenu(MENU, self.toggle_action)

        say = QAction("Say something", main_window)
        say.triggered.connect(lambda _=False: self.assistant and self.assistant.remark(force=True))
        self.iface.addPluginToMenu(MENU, say)

        settings = QAction("Settings…", main_window)
        settings.triggered.connect(lambda _=False: self.open_settings())
        self.iface.addPluginToMenu(MENU, settings)
        self.actions = [self.toggle_action, say, settings]

        self.assistant = Assistant(self.iface, self.settings)
        self.assistant.visibilityChanged.connect(self._on_visibility_changed)
        self.assistant.settingsRequested.connect(self.open_settings)
        self.rules = RuleEngine(self.iface, self.assistant, self.settings)

        if main_window.isVisible():
            QTimer.singleShot(500, self._start)
        else:
            self.iface.initializationCompleted.connect(self._on_init_completed)

    def _on_init_completed(self):
        QTimer.singleShot(1500, self._start)

    def _start(self):
        if self._started or self.assistant is None:
            return
        self._started = True
        self.rules.start()
        self.assistant.start()

    def unload(self):
        try:
            self.iface.initializationCompleted.disconnect(self._on_init_completed)
        except (TypeError, RuntimeError):
            pass
        if self.rules is not None:
            self.rules.stop()
            self.rules = None
        if self.assistant is not None:
            self.assistant.shutdown()
            self.assistant = None
        for action in self.actions:
            self.iface.removePluginMenu(MENU, action)
            self.iface.removeToolBarIcon(action)
            action.deleteLater()
        self.actions = []

    def _on_toggle(self, checked):
        if self.assistant is None:
            return
        if not self._started:
            self.settings.visible = checked
            return
        self.assistant.set_visible(checked)

    def _on_visibility_changed(self, visible):
        if self.toggle_action.isChecked() != visible:
            self.toggle_action.blockSignals(True)
            self.toggle_action.setChecked(visible)
            self.toggle_action.blockSignals(False)

    def open_settings(self):
        if self.assistant is None:
            return
        SettingsDialog(self.settings, self.assistant, self.iface.mainWindow()).exec()
