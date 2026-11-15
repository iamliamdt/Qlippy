"""Settings dialog."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from . import messages
from .comments_dialog import CommentSettingsDialog
from .settings import CHATTINESS, LEVEL_DESCRIPTIONS, LEVEL_NAMES, SIZES


class SettingsDialog(QDialog):
    def __init__(self, settings, assistant, parent=None):
        super().__init__(parent)
        self.setObjectName("QlippySettings")
        self.settings = settings
        self.assistant = assistant
        self.setWindowTitle("Qlippy settings")

        self.level = QSlider(Qt.Orientation.Horizontal)
        self.level.setRange(0, 3)
        self.level.setPageStep(1)
        self.level.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.level.setTickInterval(1)
        self.level.setValue(settings.level)
        self.level_label = QLabel()
        self.level_label.setWordWrap(True)
        self.level.valueChanged.connect(self._update_level_label)
        self._update_level_label(settings.level)

        ends = QHBoxLayout()
        ends.addWidget(QLabel("Help"))
        ends.addStretch(1)
        ends.addWidget(QLabel("Harass"))

        self.personality = QComboBox()
        for personality_id in messages.PERSONALITY_ORDER:
            self.personality.addItem(messages.PERSONALITIES[personality_id]["label"], personality_id)
        current = self.personality.findData(settings.personality)
        self.personality.setCurrentIndex(max(0, current))
        self.personality_label = QLabel()
        self.personality_label.setWordWrap(True)
        self.personality.currentIndexChanged.connect(lambda _index: self._update_personality_label())
        self._update_personality_label()

        self.chattiness = QSlider(Qt.Orientation.Horizontal)
        self.chattiness.setRange(0, len(CHATTINESS) - 1)
        self.chattiness.setPageStep(1)
        self.chattiness.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.chattiness.setTickInterval(1)
        self.chattiness.setValue(settings.chattiness)
        self.chattiness_label = QLabel()
        self.chattiness.valueChanged.connect(self._update_chattiness_label)
        self._update_chattiness_label(settings.chattiness)

        self.animations = QCheckBox("Random animations")
        self.animations.setChecked(settings.random_animations)

        self.size = QComboBox()
        self.size.addItems([name for name, _ in SIZES])
        self.size.setCurrentIndex(settings.size_index)

        self.wander = QCheckBox("Wander around the window")
        self.wander.setChecked(settings.wander)
        self.wander_home = QCheckBox("Return home after exploring")
        self.wander_home.setChecked(settings.wander_return_home)
        self.wander_idle = QCheckBox("Only wander while I'm not using the mouse")
        self.wander_idle.setChecked(settings.wander_idle_only)
        self.tint = QCheckBox("QGIS colours (green, yellow and orange tint)")
        self.tint.setChecked(settings.tint)

        self.remarks = QCheckBox("Make random remarks and tips")
        self.remarks.setChecked(settings.random_remarks)
        self.follow = QCheckBox("Eyes follow the mouse cursor")
        self.follow.setChecked(settings.follow_cursor)
        self.doze = QCheckBox("Fall asleep when you're idle")
        self.doze.setChecked(settings.doze)

        detailed = QPushButton("Detailed settings\u2026")
        detailed.setToolTip("Choose which kinds of comments Qlippy makes, and fine-tune how often per level")
        detailed.clicked.connect(lambda _=False: self._open_detailed_settings())
        reset_pos = QPushButton("Reset position")
        reset_pos.clicked.connect(lambda _=False: self.assistant.reset_position())
        extra = QHBoxLayout()
        extra.addWidget(detailed)
        extra.addWidget(reset_pos)
        extra.addStretch(1)

        form = QFormLayout()
        form.addRow("Size", self.size)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Help / Harass</b>"))
        lay.addWidget(self.level)
        lay.addLayout(ends)
        lay.addWidget(self.level_label)
        lay.addSpacing(8)
        lay.addWidget(QLabel("<b>Personality</b>"))
        lay.addWidget(self.personality)
        lay.addSpacing(4)
        lay.addWidget(self.personality_label)
        lay.addSpacing(8)
        lay.addWidget(QLabel("<b>How often Qlippy speaks and acts</b>"))
        chatty_row = QHBoxLayout()
        chatty_row.addWidget(self.chattiness, 1)
        chatty_row.addWidget(self.chattiness_label)
        lay.addLayout(chatty_row)
        lay.addSpacing(8)
        lay.addWidget(self.remarks)
        lay.addWidget(self.animations)
        lay.addWidget(self.wander)
        for option in (self.wander_home, self.wander_idle):  # only meaningful while wandering
            option_row = QHBoxLayout()
            option_row.addSpacing(20)
            option_row.addWidget(option)
            lay.addLayout(option_row)
        self.wander.toggled.connect(self._update_wander_options)
        self._update_wander_options(self.wander.isChecked())
        lay.addSpacing(8)
        lay.addLayout(form)
        lay.addWidget(self.tint)
        lay.addWidget(self.follow)
        lay.addWidget(self.doze)
        lay.addSpacing(8)
        lay.addLayout(extra)
        lay.addWidget(buttons)
        self.setMinimumWidth(380)

    def _update_wander_options(self, enabled):
        self.wander_home.setEnabled(enabled)
        self.wander_idle.setEnabled(enabled)

    def _update_level_label(self, value):
        self.level_label.setText("<b>{}</b>: {}".format(LEVEL_NAMES[value], LEVEL_DESCRIPTIONS[value]))

    def _update_personality_label(self):
        personality_id = self.personality.currentData() or "classic"
        self.personality_label.setText(messages.PERSONALITIES[personality_id]["description"])

    def _update_chattiness_label(self, value):
        self.chattiness_label.setText(CHATTINESS[value][0])
        self.chattiness_label.setMinimumWidth(80)

    def _open_detailed_settings(self):
        CommentSettingsDialog(self.settings, self).exec()

    def accept(self):
        settings = self.settings
        level_changed = self.level.value() != settings.level
        settings.random_animations = self.animations.isChecked()
        settings.size_index = self.size.currentIndex()
        settings.random_remarks = self.remarks.isChecked()
        settings.follow_cursor = self.follow.isChecked()
        settings.doze = self.doze.isChecked()
        settings.wander = self.wander.isChecked()
        settings.wander_return_home = self.wander_home.isChecked()
        settings.wander_idle_only = self.wander_idle.isChecked()
        settings.tint = self.tint.isChecked()
        settings.personality = self.personality.currentData() or "classic"
        settings.chattiness = self.chattiness.value()
        self.assistant.apply_settings()
        if level_changed:
            self.assistant.set_level(self.level.value())
        super().accept()
