"""'Detailed settings': switch individual kinds of comments on and off, and
fine-tune how often Qlippy comments at each Help/Harass level."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractSpinBox,
    QDialog,
    QDoubleSpinBox,
    QHeaderView,
    QTableWidget,
    QTabWidget,
    QWidget,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from . import messages
from .settings import FREQUENCY_DEFAULTS, FREQUENCY_LABELS, LEVEL_NAMES

COMMENT_ID_ROLE = Qt.ItemDataRole.UserRole


def _level_note(comment_id):
    rule = messages.RULES.get(comment_id)
    if rule is None or rule["min_level"] == 0:
        return ""
    return "{} and up".format(LEVEL_NAMES[rule["min_level"]])


class CommentSettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("QlippySettings")  # Qlippy doesn't peek around its own settings
        self.setWindowTitle("Qlippy: detailed settings")
        self.settings = settings
        disabled = settings.disabled_rules

        intro = QLabel("Choose which kinds of comments Qlippy makes. Some only appear at higher "
                       "Help/Harass levels. Unticking a comment here is the same as clicking "
                       "\"Don't show again\" on it.")
        intro.setWordWrap(True)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Comment", "Appears at"])
        self.tree.setRootIsDecorated(True)
        for category, comments in messages.COMMENT_CATEGORIES:
            category_item = QTreeWidgetItem(self.tree, [category, ""])
            category_item.setFlags(category_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                                   | Qt.ItemFlag.ItemIsAutoTristate)
            for comment_id, label in comments:
                item = QTreeWidgetItem(category_item, [label, _level_note(comment_id)])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(0, COMMENT_ID_ROLE, comment_id)
                item.setCheckState(0, Qt.CheckState.Unchecked if comment_id in disabled
                                   else Qt.CheckState.Checked)
        self.tree.resizeColumnToContents(0)
        self.tree.setColumnWidth(0, max(self.tree.columnWidth(0) + 40, 300))

        all_on = QPushButton("All on")
        all_on.clicked.connect(lambda _=False: self._set_all(Qt.CheckState.Checked))
        all_off = QPushButton("All off")
        all_off.clicked.connect(lambda _=False: self._set_all(Qt.CheckState.Unchecked))
        self.expand_button = QPushButton("Expand all")
        self.expand_button.clicked.connect(lambda _=False: self._toggle_expanded())
        row = QHBoxLayout()
        for button in (all_on, all_off, self.expand_button):
            row.addWidget(button)
        row.addStretch(1)

        comments_tab = QWidget()
        comments_layout = QVBoxLayout(comments_tab)
        comments_layout.addWidget(intro)
        comments_layout.addWidget(self.tree, 1)
        comments_layout.addLayout(row)

        tabs = QTabWidget()
        tabs.addTab(comments_tab, "Comments")
        tabs.addTab(self._build_frequency_tab(), "Frequency")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)
        self.resize(640, 580)

    # ------------------------------------------------------------ frequency
    def _build_frequency_tab(self):
        tab = QWidget()
        intro = QLabel("How often Qlippy comments at each Help/Harass level. Bigger gaps, multipliers and "
                       "minutes mean fewer comments. All of these are also scaled by the \"How often Qlippy "
                       "speaks and acts\" slider in the main settings.")
        intro.setWordWrap(True)
        keys = list(FREQUENCY_DEFAULTS)
        self.frequency_grid = QTableWidget(len(keys), len(LEVEL_NAMES))
        self.frequency_grid.setHorizontalHeaderLabels(LEVEL_NAMES)
        self.frequency_grid.setVerticalHeaderLabels(
            ["{} ({})".format(*FREQUENCY_LABELS[key]) for key in keys])
        self.frequency_grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.frequency_grid.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._frequency_boxes = {}
        table = self.settings.frequency_table
        for row, key in enumerate(keys):
            for level in range(len(LEVEL_NAMES)):
                box = QDoubleSpinBox()
                box.setDecimals(1 if key == "cooldown_factor" else 0)
                box.setRange(0.1 if key == "cooldown_factor" else 0.0, 100.0 if key == "cooldown_factor" else 100000.0)
                box.setSingleStep(0.1 if key == "cooldown_factor" else 1.0)
                box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                box.setValue(table[key][level])
                self.frequency_grid.setCellWidget(row, level, box)
                self._frequency_boxes[(key, level)] = box
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(lambda _=False: self._reset_frequency())
        reset_row = QHBoxLayout()
        reset_row.addWidget(reset)
        reset_row.addStretch(1)
        layout = QVBoxLayout(tab)
        layout.addWidget(intro)
        layout.addWidget(self.frequency_grid, 1)
        layout.addLayout(reset_row)
        return tab

    def _reset_frequency(self):
        for (key, level), box in self._frequency_boxes.items():
            box.setValue(FREQUENCY_DEFAULTS[key][level])

    def frequency_values(self):
        values = {key: [0.0] * len(LEVEL_NAMES) for key in FREQUENCY_DEFAULTS}
        for (key, level), box in self._frequency_boxes.items():
            values[key][level] = box.value()
        for level in range(len(LEVEL_NAMES)):  # "latest" can't be earlier than "earliest"
            values["remark_max"][level] = max(values["remark_max"][level], values["remark_min"][level])
        return values

    # -------------------------------------------------------------- comments
    def _toggle_expanded(self):
        expanded = any(self.tree.topLevelItem(i).isExpanded() for i in range(self.tree.topLevelItemCount()))
        if expanded:
            self.tree.collapseAll()
            self.expand_button.setText("Expand all")
        else:
            self.tree.expandAll()
            self.expand_button.setText("Collapse all")

    def _comment_items(self):
        for i in range(self.tree.topLevelItemCount()):
            category_item = self.tree.topLevelItem(i)
            for j in range(category_item.childCount()):
                yield category_item.child(j)

    def _set_all(self, state):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, state)

    def disabled_ids(self):
        return {item.data(0, COMMENT_ID_ROLE) for item in self._comment_items()
                if item.checkState(0) != Qt.CheckState.Checked}

    def accept(self):
        # keep any disabled ids this dialog doesn't know about (e.g. from newer versions)
        known = {item.data(0, COMMENT_ID_ROLE) for item in self._comment_items()}
        unknown = self.settings.disabled_rules - known
        self.settings.set_disabled_rules(unknown | self.disabled_ids())
        values = self.frequency_values()
        self.settings.frequency_table = {} if values == FREQUENCY_DEFAULTS else values
        super().accept()
