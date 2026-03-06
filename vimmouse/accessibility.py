"""AX tree querying and element matching."""

import ApplicationServices as AX

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
    "AXTextField",
    "AXTextArea",
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

def is_element_stale(element):
    """Check if an AX element is no longer valid or visible."""
    # Try to fetch a basic attribute; if it fails, it's likely stale
    err, _ = AX.AXUIElementCopyAttributeValue(element, "AXRole", None)
    if err != 0:
        return True
    return False

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


def _build_label(element, role):
    """Assemble a display label from an element's attributes."""
    title = _get_attr(element, "AXTitle") or ""
    desc = _get_attr(element, "AXDescription") or ""
    value = _get_attr(element, "AXValue")
    value_str = str(value) if value is not None else ""
    subrole = _get_attr(element, "AXSubrole") or ""
    help_text = _get_attr(element, "AXHelp") or ""
    label = title or desc or value_str or help_text or subrole or ""
    return label, title, desc, value_str, subrole


def _element_rect(position, size):
    """Unpack AXValue position/size into (x, y, w, h)."""
    _, p = AX.AXValueGetValue(position, AX.kAXValueCGPointType, None)
    _, s = AX.AXValueGetValue(size, AX.kAXValueCGSizeType, None)
    return (p.x, p.y, s.width, s.height)


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


def _collect_elements(root, results, parent_clickable=False):
    """Iteratively collect interactive elements from the AX tree."""
    # Use an explicit stack to avoid hitting Python's recursion limit on deep
    # web-content trees.
    stack = [(root, parent_clickable)]
    while stack:
        element, par_click = stack.pop()
        role = _get_attr(element, "AXRole")
        # Skip static text / images that are children of a clickable element (they're just labels)
        if par_click and role in ("AXStaticText", "AXImage"):
            continue

        if _is_interactive(role, element):
            position = _get_attr(element, "AXPosition")
            size = _get_attr(element, "AXSize")
            if position is not None and size is not None:
                label, title, desc, value_str, subrole = _build_label(element, role)
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
            child_click = clickable or par_click
            # Reverse so we process children in original order (stack is LIFO)
            for child in reversed(children):
                stack.append((child, child_click))


def get_elements(pid):
    """Walk the AX tree for the given PID and return interactive elements."""
    app_ref = AX.AXUIElementCreateApplication(pid)
    results = []
    _collect_elements(app_ref, results)
    return results


def _get_visible_bounds(pid):
    """Return (x, y, w, h) of the focused window frame for the given PID."""
    app_ref = AX.AXUIElementCreateApplication(pid)
    focused = _get_attr(app_ref, "AXFocusedWindow")
    if focused is None:
        return None

    pos = _get_attr(focused, "AXPosition")
    size = _get_attr(focused, "AXSize")
    if pos is None or size is None:
        return None
    return _element_rect(pos, size)


def _collect_clickable(root):
    """Fast collection: only gather clickable element refs with position/size."""
    results = []
    stack = [root]
    while stack:
        element = stack.pop()
        role = _get_attr(element, "AXRole")
        if role and _is_clickable(role, element):
            position = _get_attr(element, "AXPosition")
            size = _get_attr(element, "AXSize")
            if position is not None and size is not None:
                results.append({"element": element, "role": role,
                                "position": position, "size": size})
        children = _get_attr(element, "AXChildren")
        if not children:
            children = _get_attr(element, "AXVisibleChildren")
        if children:
            stack.extend(children)
    return results


def _enrich_element(el):
    """Fetch full label info for a verified visible element."""
    element = el["element"]
    role = el["role"]
    label, title, desc, value_str, subrole = _build_label(element, role)
    if not label:
        label = _child_text(element)
    if not label:
        label = role or "?"
    el.update({"subrole": subrole, "title": title, "description": desc,
               "value": value_str, "label": label, "clickable": True})
    return el


def get_clickable_elements(pid):
    """Get only clickable elements actually visible on screen."""
    app_ref = AX.AXUIElementCreateApplication(pid)
    candidates = _collect_clickable(app_ref)

    bounds = _get_visible_bounds(pid)
    if bounds is None:
        return [_enrich_element(el) for el in candidates]
    bx, by, bw, bh = bounds

    visible = []
    for el in candidates:
        ex, ey, ew, eh = _element_rect(el["position"], el["size"])
        if ew < 10 or eh < 10:
            continue
        if not (ex + ew > bx and ex < bx + bw
                and ey + eh > by and ey < by + bh):
            continue
        visible.append(_enrich_element(el))

    return visible


def get_all_clickable_elements(pid_bounds_map):
    """Get clickable elements for multiple PIDs, filtered by their window bounds."""
    all_elements = []
    for pid, bounds_list in pid_bounds_map.items():
        app_ref = AX.AXUIElementCreateApplication(pid)
        candidates = _collect_clickable(app_ref)
        for el in candidates:
            ex, ey, ew, eh = _element_rect(el["position"], el["size"])
            if ew < 10 or eh < 10:
                continue
            for bx, by, bw, bh in bounds_list:
                if (ex + ew > bx and ex < bx + bw
                        and ey + eh > by and ey < by + bh):
                    all_elements.append(_enrich_element(el))
                    break
    return all_elements


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
