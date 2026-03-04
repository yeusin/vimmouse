"""AX tree querying and element matching."""

import ApplicationServices as AX
from AppKit import NSWorkspace

# Semantic keyword → (AXRole, AXSubrole) or custom matcher
SEMANTIC_MAP = {
    "close": ("AXButton", "AXCloseButton"),
    "minimize": ("AXButton", "AXMinimizeButton"),
    "maximize": ("AXButton", "AXZoomButton"),
    "zoom": ("AXButton", "AXZoomButton"),
}

# Roles always considered interactive
INTERACTIVE_ROLES = {
    "AXButton",
    "AXTextField",
    "AXTextArea",
    "AXCheckBox",
    "AXRadioButton",
    "AXPopUpButton",
    "AXComboBox",
    "AXSlider",
    "AXMenuItem",
    "AXMenuBarItem",
    "AXLink",
    "AXTabGroup",
    "AXTab",
    "AXToolbar",
    "AXStaticText",
    "AXImage",
    "AXCell",
    "AXRow",
    "AXIncrementor",
    "AXColorWell",
    "AXDisclosureTriangle",
    "AXHeading",
}

# Roles that are inherently clickable
ALWAYS_CLICKABLE = {
    "AXButton",
    "AXLink",
    "AXMenuItem",
    "AXMenuBarItem",
    "AXCheckBox",
    "AXRadioButton",
    "AXPopUpButton",
    "AXComboBox",
    "AXTab",
    "AXDisclosureTriangle",
    "AXIncrementor",
    "AXColorWell",
}

# Roles that are interactive only if they have an AXPress action (web content)
CLICKABLE_IF_PRESSABLE = {
    "AXGroup",
    "AXStaticText",
    "AXImage",
    "AXHeading",
}


def _get_attr(element, attr):
    err, value = AX.AXUIElementCopyAttributeValue(element, attr, None)
    if err == 0:
        return value
    return None


def _is_clickable(role, element):
    """Check if an element can be clicked."""
    if role in ALWAYS_CLICKABLE:
        return True
    actions = _get_attr(element, "AXActionNames")
    return bool(actions and "AXPress" in actions)


def _is_interactive(role, element):
    """Check if an element is interactive based on role and actions."""
    if role in INTERACTIVE_ROLES:
        return True
    if role in CLICKABLE_IF_PRESSABLE:
        return _is_clickable(role, element)
    return False


def _child_text(element, max_depth=3):
    """Gather visible text from children (for labeling clickable containers)."""
    if max_depth <= 0:
        return ""
    children = _get_attr(element, "AXChildren")
    if not children:
        return ""
    parts = []
    for child in children:
        role = _get_attr(child, "AXRole")
        if role == "AXStaticText":
            v = _get_attr(child, "AXValue")
            if v:
                parts.append(str(v))
        elif role == "AXImage":
            d = _get_attr(child, "AXDescription") or ""
            if d:
                parts.append(d)
        else:
            parts.append(_child_text(child, max_depth - 1))
        if len(parts) >= 4:
            break
    return " ".join(p for p in parts if p)


def _collect_elements(element, results, parent_clickable=False):
    """Recursively collect interactive elements from the AX tree."""

    role = _get_attr(element, "AXRole")
    # Skip static text / images that are children of a clickable element (they're just labels)
    if parent_clickable and role in ("AXStaticText", "AXImage"):
        return

    if _is_interactive(role, element):
        position = _get_attr(element, "AXPosition")
        size = _get_attr(element, "AXSize")
        if position is not None and size is not None:
            title = _get_attr(element, "AXTitle") or ""
            desc = _get_attr(element, "AXDescription") or ""
            value = _get_attr(element, "AXValue")
            value_str = str(value) if value is not None else ""
            subrole = _get_attr(element, "AXSubrole") or ""
            help_text = _get_attr(element, "AXHelp") or ""
            label = title or desc or value_str or help_text or subrole or ""
            clickable = _is_clickable(role, element)
            # For clickable elements with no label, try to get text from children
            if not label and clickable:
                label = _child_text(element)
            # Exclude non-clickable elements with only a generic role as label
            if not label and not clickable:
                pass  # skip — no useful label and not clickable
            elif label or clickable:
                if not label:
                    label = role or "?"
                results.append(
                    {
                        "element": element,
                        "role": role or "",
                        "subrole": subrole,
                        "title": title,
                        "description": desc,
                        "value": value_str,
                        "label": label,
                        "position": position,
                        "size": size,
                        "clickable": clickable,
                    }
                )

    clickable = _is_clickable(role, element) if role else False
    children = _get_attr(element, "AXChildren")
    if children:
        for child in children:
            _collect_elements(
                child, results,
                parent_clickable=clickable or parent_clickable,
            )


def get_frontmost_pid():
    """Return the PID of the frontmost application."""
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.processIdentifier()


def get_elements(pid):
    """Walk the AX tree for the given PID and return interactive elements."""
    app_ref = AX.AXUIElementCreateApplication(pid)
    results = []
    _collect_elements(app_ref, results)
    return results


def get_window_bounds(pid):
    """Return (x, y, w, h) of the focused window for the given PID, or None."""
    app_ref = AX.AXUIElementCreateApplication(pid)
    focused = _get_attr(app_ref, "AXFocusedWindow")
    if focused is None:
        return None
    pos = _get_attr(focused, "AXPosition")
    size = _get_attr(focused, "AXSize")
    if pos is None or size is None:
        return None
    _, p = AX.AXValueGetValue(pos, AX.kAXValueCGPointType, None)
    _, s = AX.AXValueGetValue(size, AX.kAXValueCGSizeType, None)
    return (p.x, p.y, s.width, s.height)


def get_clickable_elements(pid):
    """Get only clickable elements visible within the focused window."""
    elements = [el for el in get_elements(pid) if el.get("clickable")]
    bounds = get_window_bounds(pid)
    if bounds is None:
        return elements
    wx, wy, ww, wh = bounds
    visible = []
    for el in elements:
        _, pos = AX.AXValueGetValue(el["position"], AX.kAXValueCGPointType, None)
        if wx <= pos.x < wx + ww and wy <= pos.y < wy + wh:
            visible.append(el)
    return visible


def search(query, elements):
    """Filter and rank elements by query. Returns sorted list of matches."""
    if not query:
        return elements

    query_lower = query.lower().strip()

    # Check semantic match first
    semantic = SEMANTIC_MAP.get(query_lower)

    scored = []
    for el in elements:
        score = _score_element(el, query_lower, semantic)
        if score > 0:
            scored.append((score, el))

    # Sort by score descending, clickable elements first within same score
    scored.sort(key=lambda x: (-x[0], not x[1].get("clickable", False)))
    return [el for _, el in scored]


def _score_element(el, query_lower, semantic):
    """Score an element against the query. 0 = no match."""
    # Semantic match (highest priority)
    if semantic:
        role, subrole = semantic
        if el["role"] == role and el["subrole"] == subrole:
            return 100

    # Special keyword matching for "search"
    if query_lower == "search":
        if el["role"] == "AXTextField" and el["subrole"] == "AXSearchField":
            return 100

    if query_lower == "back":
        if el["role"] == "AXButton" and "back" in el["title"].lower():
            return 100

    # Text matching against title, description, value
    score = 0
    for field in ("title", "description", "value"):
        text = el[field].lower()
        if not text:
            continue
        if text == query_lower:
            score = max(score, 90)
        elif text.startswith(query_lower):
            score = max(score, 70)
        elif query_lower in text:
            score = max(score, 50)

    # Fuzzy: all query chars appear in order
    if score == 0:
        combined = (el["title"] + el["description"] + el["value"]).lower()
        if _subsequence_match(query_lower, combined):
            score = 20

    # Boost clickable elements
    if score > 0 and el.get("clickable"):
        score += 5

    return score


def _subsequence_match(query, text):
    """Check if all chars in query appear in text in order."""
    it = iter(text)
    return all(c in it for c in query)
