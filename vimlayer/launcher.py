"""Alfred-like app/settings launcher UI."""

import json
import logging
import os

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontWeightMedium,
    NSImageView,
    NSMakeRect,
    NSMakeSize,
    NSScreen,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskBorderless,
    NSWorkspace,
)
from Foundation import NSObject, NSURL

log = logging.getLogger(__name__)

# Layout
_WIN_W = 620
_WIN_H = 460
_SEARCH_H = 48
_ROW_H = 44
_ICON_SIZE = 28
_MAX_VISIBLE = 9
_PAD = 12
_SEARCH_PAD = 16
_ICON_PAD = 14

_MEMORY_PATH = os.path.expanduser("~/.config/vimlayer/launcher_memory.json")


class _SelectionMemory:
    """Tracks how many times each item was selected for a given query."""

    def __init__(self):
        self._data = {}  # {query: {path: count}}
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
        if not query:
            return
        query = query.lower()
        if query not in self._data:
            self._data[query] = {}
        counts = self._data[query]
        counts[path] = counts.get(path, 0) + 1
        self._save()

    def get_score(self, query, path):
        if not query:
            return 0
        query = query.lower()
        return self._data.get(query, {}).get(path, 0)


# Colors
_BG = (0.11, 0.11, 0.13, 0.97)
_SEARCH_BG = (0.17, 0.17, 0.19, 1.0)
_SEARCH_TEXT = (1.0, 1.0, 1.0, 1.0)
_SEARCH_PLACEHOLDER = (0.45, 0.45, 0.50, 1.0)
_ROW_TEXT = (0.92, 0.92, 0.94, 1.0)
_ROW_SUBTITLE = (0.48, 0.48, 0.52, 1.0)
_ROW_SELECTED_BG = (0.25, 0.50, 0.95, 0.85)
_ROW_SELECTED_TEXT = (1.0, 1.0, 1.0, 1.0)
_SEPARATOR = (1.0, 1.0, 1.0, 0.06)
_SHORTCUT_TEXT = (0.40, 0.40, 0.44, 1.0)


def _color(rgba):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(*rgba)


def _fuzzy_match(query, name):
    """Simple fuzzy match: all query chars must appear in order in name."""
    query = query.lower()
    name_lower = name.lower()
    qi = 0
    for ch in name_lower:
        if qi < len(query) and ch == query[qi]:
            qi += 1
    return qi == len(query)


def _fuzzy_score(query, name):
    """Score a fuzzy match. Lower is better. Prefers prefix and consecutive matches."""
    query = query.lower()
    name_lower = name.lower()
    # Prefix match bonus
    if name_lower.startswith(query):
        return -1000 + len(name)
    # Count consecutive matches from start of words
    score = len(name)
    qi = 0
    for i, ch in enumerate(name_lower):
        if qi < len(query) and ch == query[qi]:
            if i == 0 or name_lower[i - 1] in (" ", "-", "_", "."):
                score -= 10  # word boundary bonus
            qi += 1
    return score


def _scan_apps():
    """Scan for .app bundles and .prefPane items."""
    items = []
    app_dirs = ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]
    for app_dir in app_dirs:
        if not os.path.isdir(app_dir):
            continue
        try:
            entries = os.listdir(app_dir)
        except OSError:
            continue
        for entry in entries:
            full = os.path.join(app_dir, entry)
            if entry.endswith(".app"):
                items.append((entry[:-4], full))
            elif os.path.isdir(full):
                try:
                    sub_entries = os.listdir(full)
                except OSError:
                    continue
                for sub in sub_entries:
                    if sub.endswith(".app"):
                        items.append((sub[:-4], os.path.join(full, sub)))

    pane_dir = "/System/Library/PreferencePanes"
    if os.path.isdir(pane_dir):
        try:
            for entry in os.listdir(pane_dir):
                if entry.endswith(".prefPane"):
                    items.append((entry[:-9], os.path.join(pane_dir, entry)))
        except OSError:
            pass

    finder_path = "/System/Library/CoreServices/Finder.app"
    if os.path.isdir(finder_path):
        items.append(("Finder", finder_path))

    items.sort(key=lambda x: x[0].lower())
    return items


class _LauncherWindow(NSWindow):
    """Borderless window that can become key window to accept keyboard input."""

    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return True


class _SearchFieldCell(objc.lookUpClass("NSTextFieldCell")):
    """Text field cell with left padding for the search icon area."""

    def drawingRectForBounds_(self, rect):
        r = objc.super(_SearchFieldCell, self).drawingRectForBounds_(rect)
        return NSMakeRect(r.origin.x + 36, r.origin.y, r.size.width - 40, r.size.height)

    def editWithFrame_inView_editor_delegate_event_(self, rect, view, editor, delegate, event):
        r = NSMakeRect(rect.origin.x + 36, rect.origin.y, rect.size.width - 40, rect.size.height)
        objc.super(_SearchFieldCell, self).editWithFrame_inView_editor_delegate_event_(
            r, view, editor, delegate, event
        )

    def selectWithFrame_inView_editor_delegate_start_length_(
        self, rect, view, editor, delegate, start, length
    ):
        r = NSMakeRect(rect.origin.x + 36, rect.origin.y, rect.size.width - 40, rect.size.height)
        objc.super(_SearchFieldCell, self).selectWithFrame_inView_editor_delegate_start_length_(
            r, view, editor, delegate, start, length
        )


class _SearchFieldView(NSView):
    """Rounded search field container with a magnifying glass icon."""

    def initWithFrame_(self, frame):
        self = objc.super(_SearchFieldView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.setWantsLayer_(True)
        self.layer().setCornerRadius_(10)
        self.layer().setMasksToBounds_(True)
        return self

    def drawRect_(self, rect):
        _color(_SEARCH_BG).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(self.bounds(), 10, 10).fill()
        # Draw magnifying glass icon
        _color(_SEARCH_PLACEHOLDER).set()
        cx, cy = 22, self.bounds().size.height / 2
        r = 7
        path = NSBezierPath.bezierPath()
        path.appendBezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r + 1, r * 2, r * 2))
        path.setLineWidth_(2.0)
        path.stroke()
        # Handle
        path2 = NSBezierPath.bezierPath()
        path2.moveToPoint_((cx + r * 0.65, cy - r * 0.65 + 1))
        path2.lineToPoint_((cx + r + 4, cy - r - 3))
        path2.setLineWidth_(2.5)
        path2.setLineCapStyle_(1)  # round
        path2.stroke()


class _ResultRowView(NSView):
    """A single result row with icon, name, kind label, and selection highlight."""

    def initWithFrame_(self, frame):
        self = objc.super(_ResultRowView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._selected = False
        self.setWantsLayer_(True)

        w = frame.size.width
        h = frame.size.height
        icon_y = (h - _ICON_SIZE) / 2

        # App icon
        self._icon_view = NSImageView.alloc().initWithFrame_(
            NSMakeRect(_ICON_PAD, icon_y, _ICON_SIZE, _ICON_SIZE)
        )
        self.addSubview_(self._icon_view)

        # App name
        name_x = _ICON_PAD + _ICON_SIZE + 10
        self._name_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(name_x, h / 2 - 10, w - name_x - 100, 20)
        )
        self._name_label.setEditable_(False)
        self._name_label.setSelectable_(False)
        self._name_label.setBezeled_(False)
        self._name_label.setDrawsBackground_(False)
        self._name_label.setFont_(NSFont.systemFontOfSize_weight_(14, NSFontWeightMedium))
        self._name_label.setTextColor_(_color(_ROW_TEXT))
        self._name_label.setLineBreakMode_(5)  # truncate tail
        self.addSubview_(self._name_label)

        # Kind subtitle
        self._kind_label = NSTextField.alloc().initWithFrame_(NSMakeRect(w - 95, h / 2 - 8, 80, 16))
        self._kind_label.setEditable_(False)
        self._kind_label.setSelectable_(False)
        self._kind_label.setBezeled_(False)
        self._kind_label.setDrawsBackground_(False)
        self._kind_label.setFont_(NSFont.systemFontOfSize_(11))
        self._kind_label.setTextColor_(_color(_ROW_SUBTITLE))
        self._kind_label.setAlignment_(2)  # right
        self.addSubview_(self._kind_label)

        return self

    def setSelected_(self, selected):
        self._selected = selected
        if selected:
            self._name_label.setTextColor_(_color(_ROW_SELECTED_TEXT))
        else:
            self._name_label.setTextColor_(_color(_ROW_TEXT))
        self.setNeedsDisplay_(True)

    def setItem_icon_(self, item, icon):
        name, path = item
        self._name_label.setStringValue_(name)
        if path.startswith("web:"):
            kind = "Web Search"
        else:
            kind = "Settings" if path.endswith(".prefPane") else "Application"

        self._kind_label.setStringValue_(kind)
        if icon:
            icon.setSize_(NSMakeSize(_ICON_SIZE, _ICON_SIZE))
            self._icon_view.setImage_(icon)
        else:
            self._icon_view.setImage_(None)

    def drawRect_(self, rect):
        if self._selected:
            _color(_ROW_SELECTED_BG).set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(4, 1, self.bounds().size.width - 8, self.bounds().size.height - 2), 8, 8
            ).fill()


class _SearchFieldDelegate(NSObject):
    """Delegate that handles text changes and key commands for the search field."""

    def init(self):
        self = objc.super(_SearchFieldDelegate, self).init()
        if self is None:
            return None
        self._launcher = None
        return self

    def controlTextDidChange_(self, notification):
        if self._launcher:
            self._launcher._on_query_changed()

    def control_textView_doCommandBySelector_(self, control, textView, selector):
        sel = str(selector)
        if sel == "insertNewline:":
            self._launcher._launch_selected()
            return True
        if sel == "cancelOperation:":
            self._launcher.dismiss()
            return True
        if sel == "moveUp:":
            self._launcher._move_selection(-1)
            return True
        if sel == "moveDown:":
            self._launcher._move_selection(1)
            return True
        return False


class Launcher:
    def __init__(self, on_dismiss=None):
        self._on_dismiss = on_dismiss
        self._window = None
        self._search_field = None
        self._search_delegate = None
        self._row_views = []
        self._results = []
        self._selected = 0
        self._app_cache = None
        self._icon_cache = {}
        self._scroll_offset = 0
        self._memory = _SelectionMemory()

    def show(self):
        if self._app_cache is None:
            self._app_cache = _scan_apps()
            log.info("launcher: indexed %d items", len(self._app_cache))

        if self._window is None:
            self._build_window()
        else:
            self.recenter()

        self._search_field.setStringValue_("")
        self._results = list(self._app_cache)
        self._selected = 0
        self._scroll_offset = 0
        self._update_result_display()

        NSApp.setActivationPolicy_(1)
        self._window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        self._window.makeFirstResponder_(self._search_field)

    def dismiss(self):
        if self._window:
            self._window.orderOut_(None)
        NSApp.setActivationPolicy_(2)
        if self._on_dismiss:
            self._on_dismiss()

    def recenter(self):
        """Update window position to be centered on the current main screen."""
        if not self._window:
            return
        screen = NSScreen.mainScreen().frame()
        x = screen.origin.x + (screen.size.width - _WIN_W) / 2
        y = screen.origin.y + (screen.size.height - _WIN_H) / 2 + screen.size.height * 0.1
        self._window.setFrame_display_(NSMakeRect(x, y, _WIN_W, _WIN_H), True)

    def is_visible(self):
        return self._window is not None and self._window.isVisible()

    def _get_icon(self, path):
        """Get app icon for a path, with caching."""
        icon = self._icon_cache.get(path)
        if icon is None:
            if path.startswith("web:"):
                # Use default browser icon for web search
                ws = NSWorkspace.sharedWorkspace()
                search_url = NSURL.URLWithString_("https://google.com")
                app_url = ws.URLForApplicationToOpenURL_(search_url)
                if app_url:
                    icon = ws.iconForFile_(app_url.path())
                else:
                    # Fallback to some generic icon if we can't find browser
                    icon = ws.iconForFileType_("html")
            else:
                icon = NSWorkspace.sharedWorkspace().iconForFile_(path)
            self._icon_cache[path] = icon
        return icon

    def _build_window(self):
        w = _LauncherWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _WIN_W, _WIN_H),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        w.setOpaque_(False)
        w.setBackgroundColor_(_color(_BG))
        w.setLevel_(3)  # NSFloatingWindowLevel
        w.setHasShadow_(True)
        w.setReleasedWhenClosed_(False)
        w.setMovableByWindowBackground_(True)

        self._window = w
        self.recenter()

        content = w.contentView()
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(14)
        content.layer().setMasksToBounds_(True)

        # Search field container (with magnifying glass)
        search_y = _WIN_H - _SEARCH_H - _PAD
        search_container = _SearchFieldView.alloc().initWithFrame_(
            NSMakeRect(_PAD, search_y, _WIN_W - 2 * _PAD, _SEARCH_H)
        )
        content.addSubview_(search_container)

        # Search text field inside the container
        sf_font = NSFont.systemFontOfSize_(18)
        sf_h = 24  # single-line height for 18pt font
        sf_y = search_y + (_SEARCH_H - sf_h) / 2
        sf = NSTextField.alloc().initWithFrame_(
            NSMakeRect(_PAD + 42, sf_y, _WIN_W - 2 * _PAD - 50, sf_h)
        )
        sf.setFont_(sf_font)
        sf.setTextColor_(_color(_SEARCH_TEXT))
        sf.setBackgroundColor_(NSColor.clearColor())
        sf.setDrawsBackground_(False)
        sf.setBezeled_(False)
        sf.setEditable_(True)
        sf.setSelectable_(True)
        sf.setPlaceholderString_("Search apps and settings...")
        sf.setFocusRingType_(1)  # NSFocusRingTypeNone
        sf.setUsesSingleLineMode_(True)
        sf.cell().setScrollable_(True)
        sf.cell().setWraps_(False)
        content.addSubview_(sf)

        # Separator line below search
        sep_y = search_y - 6
        sep = NSView.alloc().initWithFrame_(NSMakeRect(_PAD + 8, sep_y, _WIN_W - 2 * _PAD - 16, 1))
        sep.setWantsLayer_(True)
        sep.layer().setBackgroundColor_(_color(_SEPARATOR).CGColor())
        content.addSubview_(sep)

        # Delegate
        delegate = _SearchFieldDelegate.alloc().init()
        delegate._launcher = self
        sf.setDelegate_(delegate)
        self._search_field = sf
        self._search_delegate = delegate

        # Result rows
        self._row_views = []
        results_top = sep_y - 6
        row_w = _WIN_W - 2 * _PAD
        for i in range(_MAX_VISIBLE):
            row_y = results_top - (i + 1) * _ROW_H
            row = _ResultRowView.alloc().initWithFrame_(NSMakeRect(_PAD, row_y, row_w, _ROW_H))
            content.addSubview_(row)
            self._row_views.append(row)

        # Shortcut hint at the bottom
        hint = NSTextField.alloc().initWithFrame_(NSMakeRect(_PAD, 8, _WIN_W - 2 * _PAD, 14))
        hint.setEditable_(False)
        hint.setSelectable_(False)
        hint.setBezeled_(False)
        hint.setDrawsBackground_(False)
        hint.setFont_(NSFont.systemFontOfSize_(10.5))
        hint.setTextColor_(_color(_SHORTCUT_TEXT))
        hint.setAlignment_(1)  # center
        hint.setStringValue_("\u2191\u2193 Navigate    \u23ce Open    esc Dismiss")
        content.addSubview_(hint)

        self._window = w

    def _on_query_changed(self):
        query = str(self._search_field.stringValue())
        if not query:
            self._results = list(self._app_cache)
        else:
            matched = [(name, path) for name, path in self._app_cache if _fuzzy_match(query, name)]
            web_item = (f"Search Google for \"{query}\"", f"web:{query}")
            all_options = matched + [web_item]

            def sort_key(item):
                name, path = item
                score = self._memory.get_score(query, path)
                
                # Tie-breaking for items with same frequency:
                # 1. Prefix matches (priority 0)
                # 2. Web search (priority 1)
                # 3. Fuzzy matches (priority 2)
                if path.startswith("web:"):
                    priority = 1
                elif name.lower().startswith(query.lower()):
                    priority = 0
                else:
                    priority = 2
                
                # Secondary tie-break: fuzzy score for apps
                f_score = _fuzzy_score(query, name) if not path.startswith("web:") else 0
                
                return (-score, priority, f_score)

            all_options.sort(key=sort_key)
            self._results = all_options
                    
        self._selected = 0
        self._scroll_offset = 0
        self._update_result_display()

    def _move_selection(self, delta):
        if not self._results:
            return
        self._selected = max(0, min(len(self._results) - 1, self._selected + delta))
        if self._selected < self._scroll_offset:
            self._scroll_offset = self._selected
        elif self._selected >= self._scroll_offset + _MAX_VISIBLE:
            self._scroll_offset = self._selected - _MAX_VISIBLE + 1
        self._update_result_display()

    def _update_result_display(self):
        for i, row in enumerate(self._row_views):
            idx = self._scroll_offset + i
            if idx < len(self._results):
                item = self._results[idx]
                icon = self._get_icon(item[1])
                row.setItem_icon_(item, icon)
                row.setSelected_(idx == self._selected)
                row.setHidden_(False)
            else:
                row.setHidden_(True)

    def _launch_selected(self):
        if not self._results or self._selected >= len(self._results):
            return
        name, path = self._results[self._selected]
        query = str(self._search_field.stringValue())
        self._memory.record(query, path)
        self.dismiss()

        if path.startswith("web:"):
            query = path[4:]
            import urllib.parse

            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            log.info("launcher: searching web for %s", query)
            url = NSURL.URLWithString_(search_url)
        else:
            log.info("launcher: opening %s", path)
            url = NSURL.fileURLWithPath_(path)

        NSWorkspace.sharedWorkspace().openURL_(url)
