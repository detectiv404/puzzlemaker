"""pzlx_editor.py -- puzzle editor GUI (PySide6). Run: python pzlx_editor.py"""

import json
import os
import sys
import uuid
from datetime import datetime
from getpass import getuser
from pathlib import Path

from cryptography.fernet import InvalidToken
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,  # The dropdown. addItem(text, hiddenData): show one thing, store another.
    QDialog,  # A popup window. exec() shows it and pauses everything until it's closed.
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,  # A scrollable list of items (we use it for attachments).
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolBar,
    QVBoxLayout,  # Stacks widgets in a column. (QHBoxLayout = row.)
    QWidget,
)

import encrypt
import pzlx

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
LEVEL_MIN, LEVEL_MAX, LEVEL_STEP = (
    100,
    3000,
    100,
)  # Set LEVEL_STEP = 1 for every single value
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp)"

BASE_DIR = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).parent
)
CONFIG_PATH = BASE_DIR / "config.json"


def resource(name):
    """Bundled files live in sys._MEIPASS when packaged, next to the script otherwise."""
    return str(Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name)


DEFAULT_CONFIG = {}


def load_config():
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as error:
            print(f"Could not read {CONFIG_PATH.name}: {error}")
    return config


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


KEYS_PATH = BASE_DIR / "keys.json"


def load_keys():
    if KEYS_PATH.exists():
        try:
            return json.loads(KEYS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            print(f"Could not read {KEYS_PATH.name}: {error}")
    return {}


def get_or_create_key(puzzle_id):
    keys = load_keys()
    if puzzle_id not in keys:
        keys[puzzle_id] = encrypt.generate_key()
        KEYS_PATH.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    return keys[puzzle_id]

def set_key(puzzle_id, key):
    keys = load_keys()
    keys[puzzle_id] = key
    KEYS_PATH.write_text(json.dumps(keys, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Puzzle data
# ---------------------------------------------------------------------------
def timestamp():
    """Local time with timezone, e.g. 2026-09-29T14:03:07+03:00"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def blank_puzzle():
    """A fresh puzzle. date_created is stamped HERE, once, and never touched again.
    last_modified stays empty until the first save."""
    return {
        "id": uuid.uuid4().hex,
        "format": "pzl",
        "version": 1,
        "title": "",
        "attachments": [],  # Absolute paths of images, any number
        "author": getuser(),
        "date_created": timestamp(),
        "last_modified": "",
        "level": 800,
        "description": "",
        "objective": "",
        "solution": "",
        "time_limit": "",
    }


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class PuzzleEditor(QMainWindow):
    # Class attribute: ONE list shared by every window. Python deletes objects nobody
    # references, and a window with no references vanishes right after opening.
    # Keeping them here stops that.
    windows = []

    def __init__(self, config, puzzle_data=None, path=None):
        super().__init__()
        self.config = config

        self.setWindowTitle("Puzzle Maker")
        self.resize(600, 700)

        if puzzle_data is None:
            puzzle_data = blank_puzzle()
        self.puzzle_data = puzzle_data
        self.current_path = path
        self.attachments = []  # Absolute image paths currently attached

        self._build_toolbar()
        self._build_form()

        self.data_to_form()
        self._mark_clean()
        PuzzleEditor.windows.append(self)

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------
    def _build_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        buttons = [
            ("New", QKeySequence.StandardKey.New, self.on_new),
            ("Open", QKeySequence.StandardKey.Open, self.on_open),
            ("Save", QKeySequence.StandardKey.Save, self.on_save),
            ("Save As", QKeySequence.StandardKey.SaveAs, self.on_save_as),
            ("Show private key", None, self.on_show_key),
            ("Enter key", None, self.on_enter_key),
        ]
        for text, shortcut, slot in buttons:
            action = QAction(text, self)
            if shortcut is not None:
                action.setShortcut(shortcut)
            action.triggered.connect(slot)
            toolbar.addAction(action)

    def _build_form(self):
        container = QWidget()
        form = QFormLayout(container)
        # WrapAllRows = every label sits ABOVE its box instead of to the left.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(
            "Enter a clear and concise title for your puzzle..."
        )

        self.level_combo = QComboBox()
        for value in range(LEVEL_MIN, LEVEL_MAX + 1, LEVEL_STEP):
            self.level_combo.addItem(
                str(value), value
            )  # (what the user sees, what we read back)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText(
            "This is where you type all the details of your puzzle. Do not write the objective of the puzzle here"
        )

        self.objective_edit = QPlainTextEdit()
        self.objective_edit.setPlaceholderText(
            "Enter the required/objective of the puzzle here. Make it clear and concise, preferably a 'Find the...' or 'Identify...'"
        )

        self.solution_edit = QPlainTextEdit()
        self.solution_edit.setPlaceholderText(
            "Enter the solution to the puzzle.\nThis is encrypted and cannot be seen by ninedo unless you give him your key.\nMake solution as detailed as possible, showing clear reasoning steps into how the puzzle would be solved"
        )

        self.time_limit_edit = QLineEdit()
        self.time_limit_edit.setPlaceholderText("e.g. 3 days")

        # Attachments: a list on top, two buttons underneath (layouts nest like Russian dolls)
        self.attachment_list = QListWidget()
        self.attachment_list.setIconSize(QSize(48, 48))
        self.attachment_list.setFixedHeight(130)
        self.attachment_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )  # Ctrl/Shift-click

        add_button = QPushButton("Add images...")
        add_button.clicked.connect(self.on_add_attachments)
        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(self.on_remove_attachments)

        attachment_buttons = QHBoxLayout()
        attachment_buttons.addWidget(add_button)
        attachment_buttons.addWidget(remove_button)
        attachment_buttons.addStretch()

        attachment_box = QVBoxLayout()
        attachment_box.addWidget(self.attachment_list)
        attachment_box.addLayout(attachment_buttons)

        form.addRow("Title:", self.title_edit)
        form.addRow("Puzzle rating:", self.level_combo)
        form.addRow("Attachments:", attachment_box)
        form.addRow("Description:", self.description_edit)
        form.addRow("Objective:", self.objective_edit)
        form.addRow("Solution:", self.solution_edit)
        form.addRow("Time limit:", self.time_limit_edit)

        self.setCentralWidget(container)

    # -----------------------------------------------------------------------
    # Data <-> GUI
    # -----------------------------------------------------------------------
    def form_to_data(self):
        """GUI -> dict. Call right before saving."""
        self.puzzle_data["title"] = self.title_edit.text()
        self.puzzle_data["level"] = self.level_combo.currentData()

        self.puzzle_data["attachments"] = [
            f"attachments/{Path(a).name}" for a in self.attachments
        ]

        self.puzzle_data["description"] = self.description_edit.toPlainText()
        self.puzzle_data["objective"] = self.objective_edit.toPlainText()
        self.puzzle_data.setdefault("id", uuid.uuid4().hex)  # older files have no id
        key = get_or_create_key(self.puzzle_data["id"])
        if not self.solution_locked:
            self.puzzle_data.setdefault("id", uuid.uuid4().hex)
            key = get_or_create_key(self.puzzle_data["id"])
            self.puzzle_data["solution"] = encrypt.encrypt_text(self.solution_edit.toPlainText(), key)
        self.puzzle_data["time_limit"] = self.time_limit_edit.text()

    def data_to_form(self):
        """dict -> GUI. Call right after opening a file or making a new puzzle."""
        self.title_edit.setText(self.puzzle_data.get("title", ""))

        level = self.puzzle_data.get("level", 800)
        index = self.level_combo.findData(level)
        if (
            index == -1
        ):  # A value that isn't a step (e.g. 847): add it instead of silently changing it
            self.level_combo.addItem(str(level), level)
            index = self.level_combo.count() - 1
        self.level_combo.setCurrentIndex(index)

        self.attachments = list(
            self.puzzle_data.get("attachments", [])
        )  # list() = a copy, not an alias
        self._refresh_attachments()

        self.description_edit.setPlainText(self.puzzle_data.get("description", ""))
        self.objective_edit.setPlainText(self.puzzle_data.get("objective", ""))

        encrypted = self.puzzle_data.get("solution", "")
        key = load_keys().get(self.puzzle_data.get("id", ""))
        self.solution_edit.setReadOnly(False)
        self.solution_locked = False
        if not encrypted:
            self.solution_edit.setPlainText("")
        elif key is None:
            self._lock_solution()
        else:
            try:
                self.solution_edit.setPlainText(encrypt.decrypt_text(encrypted, key))
            except InvalidToken:
                self._lock_solution()

        self.time_limit_edit.setText(self.puzzle_data.get("time_limit", ""))

    def _lock_solution(self):
        self.solution_edit.setPlainText("Solution is encrypted! Ask owner for key")
        self.solution_edit.setReadOnly(True)  # can't type over the placeholder
        self.solution_locked = True
    # -----------------------------------------------------------------------
    # Attachments
    # -----------------------------------------------------------------------
    def on_add_attachments(self):
        # getOpenFileNames (plural!) lets the user select many files at once
        paths, _ = QFileDialog.getOpenFileNames(self, "Add images", "", IMAGE_FILTER)
        for path in paths:
            path = os.path.abspath(path)
            if path not in self.attachments:  # No duplicates
                self.attachments.append(path)
        self._refresh_attachments()

    def on_remove_attachments(self):
        rows = [
            self.attachment_list.row(item)
            for item in self.attachment_list.selectedItems()
        ]
        # Delete from the END: removing item 2 first would shift item 5 to position 4
        for row in sorted(rows, reverse=True):
            del self.attachments[row]
        self._refresh_attachments()

    def _refresh_attachments(self):
        """Redraws the list widget from self.attachments (the list is the truth, the widget is the picture)."""
        self.attachment_list.clear()
        for path in self.attachments:
            item = QListWidgetItem(QIcon(path), os.path.basename(path))
            item.setToolTip(path)  # Hover to see the full path
            self.attachment_list.addItem(item)

    # -----------------------------------------------------------------------
    # "Unsaved changes" tracking
    # -----------------------------------------------------------------------
    def _form_state(self):
        """A snapshot of everything the user can edit, as one comparable tuple."""
        return (
            self.title_edit.text(),
            self.level_combo.currentData(),
            tuple(self.attachments),
            self.description_edit.toPlainText(),
            self.objective_edit.toPlainText(),
            self.solution_edit.toPlainText(),
            self.time_limit_edit.text(),
        )

    def _mark_clean(self):
        """Call after new / open / save: 'what's on screen now equals what's on disk'."""
        self._clean_state = self._form_state()

    def is_modified(self):
        # No per-widget "textChanged" wiring needed: just compare against the last clean snapshot.
        # Bonus: type a letter, delete it, and it's correctly "unmodified" again.
        return self._form_state() != self._clean_state

    def _stamp_modified(self):
        """last_modified changes only when something really changed (or on the very first save)."""
        if self.is_modified() or not self.puzzle_data.get("last_modified"):
            self.puzzle_data["last_modified"] = timestamp()

    def _resolve_unsaved(self):
        """Returns True if it's safe to throw away what's on screen (nothing unsaved,
        saved just now, or the user chose Discard). False means 'stop, user cancelled'."""
        if not self.is_modified():
            return True

        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText("This puzzle has unsaved changes.")
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        save_as = box.addButton("Save As...", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)  # Esc / the X on the popup = Cancel
        box.exec()

        clicked = box.clickedButton()
        if clicked is save:
            return self.on_save()  # Returns False if they cancel the file dialog
        if clicked is save_as:
            return self.on_save_as()
        return clicked is discard

    def closeEvent(self, event):
        """Qt calls this whenever the window is about to close (X button, Alt+F4...).
        event.accept() = 'fine, close', event.ignore() = 'nope, stay open'."""
        if self._resolve_unsaved():
            PuzzleEditor.windows.remove(self)
            event.accept()
        else:
            event.ignore()

    # -----------------------------------------------------------------------
    # Toolbar slots
    # -----------------------------------------------------------------------
    def on_new(self):
        if not self._resolve_unsaved():
            return
        self.puzzle_data = blank_puzzle()
        self.current_path = None
        self.data_to_form()
        self._mark_clean()

    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open puzzle", "", "Puzzle files (*.pzl)"
        )
        if not path:
            return
        # A brand-new window gets the loaded puzzle; this one is left untouched.
        window = PuzzleEditor(self.config, pzlx.open_pzlx(path), path)
        window.show()

    def on_save(self):
        """Returns True if saved, False if the user cancelled."""
        self.form_to_data()
        if self.current_path is None:
            return self.on_save_as()
        if not self.is_modified():
            return (
                True  # Nothing changed: don't rewrite the file or touch last_modified
            )
        self._stamp_modified()
        pzlx.create_pzlx(self.puzzle_data, self.current_path, self.attachments)
        self._mark_clean()
        return True

    def on_save_as(self):
        """Returns True if saved, False if the user cancelled."""
        self.form_to_data()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save puzzle as", "", "Puzzle files (*.pzl)"
        )
        if not path:
            return False
        self._stamp_modified()
        if not path.endswith(".pzl"):
            path += ".pzl"
        self.current_path = path
        pzlx.create_pzlx(self.puzzle_data, path, self.attachments)
        self._mark_clean()
        return True

    def on_show_key(self):
        key = load_keys().get(self.puzzle_data.get("id", ""))
        if key is None:
            QMessageBox.information(
                self, "Private key", "This puzzle has no key yet. Save it first if it's yours or enter key if it's not yours."
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Private key")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("here's your private key to the puzzle"))

        key_edit = QLineEdit(key)
        key_edit.setReadOnly(True)  # selectable and copyable, but not editable
        key_edit.setMinimumWidth(460)
        layout.addWidget(key_edit)

        copy_button = QPushButton("Copy")
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(key))
        layout.addWidget(copy_button)

        dialog.exec()

    def on_enter_key(self):
        puzzle_id = self.puzzle_data.get("id")
        encrypted = self.puzzle_data.get("solution", "")
        if not puzzle_id or not encrypted:
            QMessageBox.information(self, "Enter key", "This puzzle has no encrypted solution to unlock.")
            return

        key, ok = QInputDialog.getText(self, "Enter key", "Paste the private key for this puzzle:")
        key = key.strip()
        if not ok or not key:
            return

        try:
            solution = encrypt.decrypt_text(encrypted, key)  # the test: does this key actually work?
        except (InvalidToken, ValueError):  # wrong key / malformed key
            QMessageBox.warning(self, "Enter key", "That key doesn't unlock this puzzle.")
            return

        set_key(puzzle_id, key)
        self.solution_locked = False
        self.solution_edit.setReadOnly(False)
        self.solution_edit.setPlainText(solution)
        self._mark_clean()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource("puzzlemaker.ico")))
    config = load_config()

    window = PuzzleEditor(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
