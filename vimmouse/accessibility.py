"""AX tree querying and element matching."""

import os
import objc
import Quartz
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    AXUIElementPerformAction,
    AXValueGetValue,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

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
    err, value = AXUIElementCopyAttributeValue(element, attr, None)
    if err == 0:
        return value
    return None

def is_element_stale(element):
    """Check if an AX element is no longer valid or visible."""
    # Try to fetch a basic attribute; if it fails, it's likely stale
    err, _ = AXUIElementCopyAttributeValue(element, "AXRole", None)
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
    _, p = AXValueGetValue(position, kAXValueCGPointType, None)
    _, s = AXValueGetValue(size, kAXValueCGSizeType, None)
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


def _collect_clickable(root):
    """Fast collection: only gather clickable element refs with position/size."""
    results = []
    stack = [(root, None)]  # (element, clickable_ancestor)
    while stack:
        element, clickable_ancestor = stack.pop()

        if _get_attr(element, "AXHidden"):
            continue

        role = _get_attr(element, "AXRole")
        is_direct = _is_clickable(role, element) if role else False
        
        # Determine if we should consider this element as a candidate
        effective_clickable = is_direct or (clickable_ancestor is not None)

        if role and effective_clickable:
            position = _get_attr(element, "AXPosition")
            size = _get_attr(element, "AXSize")
            if position is not None and size is not None:
                results.append({"element": element, "role": role,
                                "position": position, "size": size,
                                "is_direct": is_direct})

        # Traverse children
        children = _get_attr(element, "AXChildren")
        if children:
            new_ancestor = element if is_direct else clickable_ancestor
            for child in reversed(children):
                stack.append((child, new_ancestor))
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
               "value": value_str, "label": label, "clickable": el.get("is_direct", True)})
    return el


def _get_on_screen_windows():
    """Get all on-screen windows in front-to-back order (Quartz)."""
    return Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )


def _get_visible_bounds(pid):
    """Return (x, y, w, h) of the focused window frame for the given PID."""
    app_ref = AXUIElementCreateApplication(pid)
    focused = _get_attr(app_ref, "AXFocusedWindow")
    if focused is None:
        return None

    pos = _get_attr(focused, "AXPosition")
    size = _get_attr(focused, "AXSize")
    if pos is None or size is None:
        return None
    return _element_rect(pos, size)


def _is_element_covered(ex, ey, ew, eh, pid, win_list):
    """Check if the element's center point is covered by a window in front of it."""
    cx, cy = ex + ew / 2, ey + eh / 2
    my_pid = os.getpid()

    # The win_list is front-to-back.
    for w in win_list:
        w_pid = w.get(Quartz.kCGWindowOwnerPID, 0)
        if w_pid == my_pid:
            continue

        layer = w.get(Quartz.kCGWindowLayer, 0)
        # Skip desktop, cursor, etc. (negative layers)
        if layer < 0:
            continue

        b = w.get(Quartz.kCGWindowBounds, {})
        wx, wy, ww, wh = b.get("X", 0), b.get("Y", 0), b.get("Width", 0), b.get("Height", 0)

        # Check if this window contains the point
        if wx <= cx <= wx + ww and wy <= cy <= wy + wh:
            if w_pid == pid:
                # Target app's window is in front. We assume it's the one we're interested in.
                return False
            else:
                # Another app's window is in front. 
                # Ignore very small windows (likely tooltips or overlays)
                if ww < 50 or wh < 50:
                    continue
                if layer == 0:
                    return True

    return False


def get_clickable_elements(pid):
    """Get only clickable elements actually visible on screen."""
    app_ref = AXUIElementCreateApplication(pid)
    candidates = _collect_clickable(app_ref)

    bounds = _get_visible_bounds(pid)
    if bounds is None:
        return [_enrich_element(el) for el in candidates]
    bx, by, bw, bh = bounds

    win_list = _get_on_screen_windows()

    visible = []
    for el in candidates:
        ex, ey, ew, eh = _element_rect(el["position"], el["size"])
        
        # Lower threshold for small clickable items (like icons)
        if ew < 4 or eh < 4:
            continue
            
        # Check window bounds first (fast)
        if not (ex + ew > bx and ex < bx + bw
                and ey + eh > by and ey < by + bh):
            continue

        # Check occlusion by other windows (slower)
        if _is_element_covered(ex, ey, ew, eh, pid, win_list):
            continue

        visible.append(_enrich_element(el))

    # Spatial Deduplication: pick the best element if multiple share nearly the same center.
    # Prioritize: is_direct > role in ALWAYS_CLICKABLE > larger area
    visible.sort(key=lambda x: (
        not x.get("is_direct", False),
        x["role"] not in ALWAYS_CLICKABLE,
        - (float(_get_attr(x["element"], "AXSize").width if _get_attr(x["element"], "AXSize") else 0) * 
           float(_get_attr(x["element"], "AXSize").height if _get_attr(x["element"], "AXSize") else 0))
    ))
    
    final_visible = []
    seen_centers = []
    
    for el in visible:
        ex, ey, ew, eh = _element_rect(el["position"], el["size"])
        cx, cy = ex + ew / 2, ey + eh / 2
        
        is_dup = False
        for scx, scy in seen_centers:
            if abs(cx - scx) < 10 and abs(cy - scy) < 10:
                is_dup = True
                break
        if not is_dup:
            final_visible.append(el)
            seen_centers.append((cx, cy))

    return final_visible


def get_all_clickable_elements(pid_bounds_map):
    """Get clickable elements for multiple PIDs, filtered by their window bounds."""
    all_elements = []
    win_list = _get_on_screen_windows()

    for pid, bounds_list in pid_bounds_map.items():
        app_ref = AXUIElementCreateApplication(pid)
        candidates = _collect_clickable(app_ref)
        
        visible = []
        for el in candidates:
            ex, ey, ew, eh = _element_rect(el["position"], el["size"])
            if ew < 4 or eh < 4:
                continue

            # Within bounds of any of its app windows?
            in_any_bounds = False
            for bx, by, bw, bh in bounds_list:
                if (ex + ew > bx and ex < bx + bw
                        and ey + eh > by and ey < by + bh):
                    in_any_bounds = True
                    break

            if not in_any_bounds:
                continue

            # Check occlusion
            if _is_element_covered(ex, ey, ew, eh, pid, win_list):
                continue

            visible.append(_enrich_element(el))
            
        # Spatial Deduplication
        visible.sort(key=lambda x: (
            not x.get("is_direct", False),
            x["role"] not in ALWAYS_CLICKABLE
        ))
        
        seen_centers = []
        for el in visible:
            ex, ey, ew, eh = _element_rect(el["position"], el["size"])
            cx, cy = ex + ew / 2, ey + eh / 2
            
            is_dup = False
            for scx, scy in seen_centers:
                if abs(cx - scx) < 10 and abs(cy - scy) < 10:
                    is_dup = True
                    break
            if not is_dup:
                all_elements.append(el)
                seen_centers.append((cx, cy))
                
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
