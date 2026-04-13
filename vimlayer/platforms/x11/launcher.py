"""X11 implementation of app/settings launcher UI using PyQt6."""

import json
import logging
import os
import subprocess
from typing import List, Tuple, Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, 
    QFrame, QApplication, QScrollArea, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent
from PyQt6.QtGui import QIcon, QColor, QPalette, QFont, QKeyEvent, QPixmap

log = logging.getLogger(__name__)

# Layout defaults (matching macOS scale where possible)
_WIN_W = 620
_WIN_H = 460
_MAX_VISIBLE = 9
_MEMORY_PATH = os.path.expanduser("~/.config/vimlayer/launcher_memory.json")

class SelectionMemory:
    def __init__(self):
        self._data = {}
        self._load()

    def _load(self):
        if os.path.exists(_MEMORY_PATH):
            try:
                with open(_MEMORY_PATH, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(_MEMORY_PATH), exist_ok=True)
            with open(_MEMORY_PATH, "w") as f:
                json.dump(self._data, f)
        except OSError:
            pass

    def record(self, query, path):
        if not query: return
        query = query.lower()
        if query not in self._data: self._data[query] = {}
        counts = self._data[query]
        counts[path] = counts.get(path, 0) + 1
        self._save()

    def get_score(self, query, path):
        if not query: return 0
        query = query.lower()
        return self._data.get(query, {}).get(path, 0)

def _fuzzy_match(query, name):
    query = query.lower()
    name_lower = name.lower()
    qi = 0
    for ch in name_lower:
        if qi < len(query) and ch == query[qi]:
            qi += 1
    return qi == len(query)

def _fuzzy_score(query, name):
    query = query.lower()
    name_lower = name.lower()
    if name_lower.startswith(query):
        return -1000 + len(name)
    score = len(name)
    qi = 0
    for i, ch in enumerate(name_lower):
        if qi < len(query) and ch == query[qi]:
            if i == 0 or name_lower[i - 1] in (" ", "-", "_", "."):
                score -= 10
            qi += 1
    return score

def _scan_apps() -> List[Tuple[str, str]]:
    """Scan for .desktop files."""
    items = []
    dirs = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications")
    ]
    seen_execs = set()
    for d in dirs:
        if not os.path.isdir(d): continue
        for entry in os.listdir(d):
            if not entry.endswith(".desktop"): continue
            path = os.path.join(d, entry)
            try:
                with open(path, "r") as f:
                    name = None
                    exec_cmd = None
                    icon = None
                    for line in f:
                        if line.startswith("Name="): name = line[5:].strip()
                        elif line.startswith("Exec="): exec_cmd = line[5:].strip()
                        elif line.startswith("Icon="): icon = line[5:].strip()
                        if name and exec_cmd: break
                    
                    if name and exec_cmd:
                        # Simple de-duplication by name/exec
                        if name not in seen_execs:
                            items.append((name, f"app:{exec_cmd}"))
                            seen_execs.add(name)
            except Exception:
                continue
    items.sort(key=lambda x: x[0].lower())
    return items

class ResultItemWidget(QWidget):
    def __init__(self, name, path, icon_name=None):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(28, 28)
        if icon_name:
            self.icon_label.setPixmap(QIcon.fromTheme(icon_name).pixmap(28, 28))
        layout.addWidget(self.icon_label)
        
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: white; font-weight: 500; font-size: 14px;")
        layout.addWidget(self.name_label)
        
        layout.addStretch()
        
        kind = "Application"
        if path.startswith("web:"): kind = "Web Search"
        elif path.startswith("calc:"): kind = "Calculator"
        
        self.kind_label = QLabel(kind)
        self.kind_label.setStyleSheet("color: rgba(255, 255, 255, 120); font-size: 11px;")
        layout.addWidget(self.kind_label)

class X11Launcher(QWidget):
    def __init__(self, on_dismiss=None):
        super().__init__()
        self._on_dismiss = on_dismiss
        self._memory = SelectionMemory()
        self._app_cache = None
        self._results = []
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.resize(_WIN_W, _WIN_H)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.container = QFrame()
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            QFrame#container {
                background-color: rgba(28, 28, 33, 245);
                border-radius: 14px;
            }
        """)
        layout.addWidget(self.container)
        
        inner_layout = QVBoxLayout(self.container)
        inner_layout.setContentsMargins(12, 12, 12, 12)
        
        # Search field
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search apps and settings...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: rgb(43, 43, 48);
                color: white;
                border-radius: 10px;
                padding: 12px 12px 12px 40px;
                font-size: 18px;
                border: none;
            }
        """)
        self.search_input.textChanged.connect(self._on_query_changed)
        inner_layout.addWidget(self.search_input)
        
        # List
        self.result_list = QListWidget()
        self.result_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                border-radius: 8px;
                margin: 2px 4px;
            }
            QListWidget::item:selected {
                background-color: rgba(64, 128, 242, 210);
            }
        """)
        self.result_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.result_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner_layout.addWidget(self.result_list)
        
        # Hint
        self.hint_label = QLabel("↑↓ Navigate    ↵ Open    esc Dismiss")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet("color: rgba(255, 255, 255, 100); font-size: 10px; margin-top: 8px;")
        inner_layout.addWidget(self.hint_label)

    def show_launcher(self):
        if self._app_cache is None:
            self._app_cache = _scan_apps()
            
        self._center_on_screen()
        self.search_input.clear()
        self._on_query_changed("")
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2 - screen.height() // 10
        )

    def _on_query_changed(self, query):
        if not query:
            matched = list(self._app_cache)
        else:
            matched = [(name, path) for name, path in self._app_cache if _fuzzy_match(query, name)]
            
            # Simple web search fallback
            matched.append((f"Search Google for \"{query}\"", f"web:{query}"))

            def sort_key(item):
                name, path = item
                score = self._memory.get_score(query, path)
                if path.startswith("web:"): priority = 1
                elif name.lower().startswith(query.lower()): priority = 0
                else: priority = 2
                f_score = _fuzzy_score(query, name) if not path.startswith("web:") else 0
                return (-score, priority, f_score)

            matched.sort(key=sort_key)

        self._results = matched
        self.result_list.clear()
        for name, path in self._results[:_MAX_VISIBLE]:
            item = QListWidgetItem(self.result_list)
            widget = ResultItemWidget(name, path)
            item.setSizeHint(widget.sizeHint())
            self.result_list.addItem(item)
            self.result_list.setItemWidget(item, widget)
        
        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            if self._on_dismiss: self._on_dismiss()
        elif event.key() == Qt.Key.Key_Return:
            self._launch_selected()
        elif event.key() == Qt.Key.Key_Up:
            self.result_list.setCurrentRow(max(0, self.result_list.currentRow() - 1))
        elif event.key() == Qt.Key.Key_Down:
            self.result_list.setCurrentRow(min(self.result_list.count() - 1, self.result_list.currentRow() + 1))
        else:
            super().keyPressEvent(event)

    def _launch_selected(self):
        row = self.result_list.currentRow()
        if row < 0 or row >= len(self._results): return
        
        name, path = self._results[row]
        query = self.search_input.text()
        self._memory.record(query, path)
        
        self.hide()
        if self._on_dismiss: self._on_dismiss()
        
        if path.startswith("app:"):
            cmd = path[4:]
            # Strip potential % arguments from desktop file Exec
            cmd = cmd.split(" %")[0]
            log.info("launching: %s", cmd)
            subprocess.Popen(cmd.split(), start_new_session=True)
        elif path.startswith("web:"):
            import urllib.parse
            url = f"https://www.google.com/search?q={urllib.parse.quote(path[4:])}"
            subprocess.Popen(["xdg-open", url])

    def hideEvent(self, event):
        if self._on_dismiss:
            self._on_dismiss()
        super().hideEvent(event)
