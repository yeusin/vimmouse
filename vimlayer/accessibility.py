"""AX tree querying and element matching."""

import os
import objc
from typing import Any, Dict, List, Optional, Tuple
import Quartz
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateSystemWide,
    AXUIElementGetPid,
    AXValueGetValue,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

# Private API: _AXUIElementGetWindow(AXUIElementRef, CGWindowID *) -> AXError
try:
    _hi_bundle = objc.loadBundle(
        "HIServices", {},
        bundle_path="/System/Library/Frameworks/ApplicationServices.framework/"
                    "Frameworks/HIServices.framework",
    )
    _fn = {}
    objc.loadBundleFunctions(_hi_bundle, _fn, [("_AXUIElementGetWindow", b"l@o^I")])
    _AXUIElementGetWindow = _fn["_AXUIElementGetWindow"]
except (ImportError, KeyError, AttributeError):
    _AXUIElementGetWindow = None


def get_window_id(element: Any) -> Optional[int]:
    """Get the CGWindowID of the window containing this element."""
    if _AXUIElementGetWindow is None:
        return None
    err, wid = _AXUIElementGetWindow(element, None)
    if err == 0:
        return wid
    return None

# Semantic keyword → (AXRole, AXSubrole) or custom matcher
SEMANTIC_MAP: Dict[str, Tuple[str, str]] = {
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
    "AXSearchField",
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
    "AXSearchField",
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


# Roles that should trigger auto-insert mode
INPUT_ROLES = {
    "AXTextField",
    "AXTextArea",
    "AXSearchField",
    "AXComboBox",
}


def is_input_element(element: Any) -> bool:
    """Check if an element is a text input."""
    role = _get_attr(element, "AXRole")
    if role in INPUT_ROLES:
        return True
    subrole = _get_attr(element, "AXSubrole")
    if subrole == "AXSearchField":
        return True
    return False


def get_focused_element() -> Optional[Any]:
    """Get the globally focused UI element."""
    system_wide = AXUIElementCreateSystemWide()
    err, element = AXUIElementCopyAttributeValue(system_wide, "AXFocusedUIElement", None)
    if err == 0:
        return element
    return None


def get_element_pid(element: Any) -> Optional[int]:
    """Get the PID of the application owning this element."""
    err, pid = AXUIElementGetPid(element, None)
    if err == 0:
        return pid
    return None


def _get_attr(element: Any, attr: str) -> Any:
    err, value = AXUIElementCopyAttributeValue(element, attr, None)
    if err == 0:
        return value
    return None

def is_element_stale(element: Any) -> bool:
    """Check if an AX element is no longer valid or visible."""
    # Try to fetch a basic attribute; if it fails, it's likely stale
    err, _ = AXUIElementCopyAttributeValue(element, "AXRole", None)
    if err != 0:
        return True
    return False

def _is_clickable(role: str, element: Any) -> bool:
    """Check if an element can be clicked."""
    if role in ALWAYS_CLICKABLE:
        return True
    actions = _get_attr(element, "AXActionNames")
    return bool(actions and "AXPress" in actions)


def _is_interactive(role: str, element: Any) -> bool:
    """Check if an element is interactive based on role and actions."""
    if role in INTERACTIVE_ROLES:
        return True
    if role in CLICKABLE_IF_PRESSABLE:
        return _is_clickable(role, element)
    return False


def _build_label(element: Any, role: str) -> Tuple[str, str, str, str, str]:
    """Assemble a display label from an element's attributes."""
    title = _get_attr(element, "AXTitle") or ""
    desc = _get_attr(element, "AXDescription") or ""
    value = _get_attr(element, "AXValue")
    value_str = str(value) if value is not None else ""
    subrole = _get_attr(element, "AXSubrole") or ""
    help_text = _get_attr(element, "AXHelp") or ""
    label = title or desc or value_str or help_text or subrole or ""
    return label, title, desc, value_str, subrole


def _element_rect(position: Any, size: Any) -> Tuple[float, float, float, float]:
    """Unpack AXValue position/size into (x, y, w, h)."""
    _, p = AXValueGetValue(position, kAXValueCGPointType, None)
    _, s = AXValueGetValue(size, kAXValueCGSizeType, None)
    return (p.x, p.y, s.width, s.height)


def _child_text(element: Any, max_depth: int = 3) -> str:
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


def _collect_clickable(root: Any) -> List[Dict[str, Any]]:
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


def _enrich_element(el: Dict[str, Any]) -> Dict[str, Any]:
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


def _get_on_screen_windows() -> List[Dict[str, Any]]:
    """Get all on-screen windows in front-to-back order (Quartz)."""
    return Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )


def _get_visible_bounds(pid: int) -> Optional[Tuple[float, float, float, float]]:
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


def _is_element_covered(ex: float, ey: float, ew: float, eh: float, pid: int, win_list: List[Dict[str, Any]], target_wid: Optional[int] = None) -> bool:
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

        w_id = w.get(Quartz.kCGWindowNumber, 0)
        b = w.get(Quartz.kCGWindowBounds, {})
        wx, wy, ww, wh = b.get("X", 0), b.get("Y", 0), b.get("Width", 0), b.get("Height", 0)

        # Check if this window contains the point
        if wx <= cx <= wx + ww and wy <= cy <= wy + wh:
            if w_pid == pid:
                if target_wid is not None:
                    if w_id == target_wid:
                        # Target app's same window is in front. We're on it.
                        return False
                    else:
                        # Another window of target app is in front. Covered!
                        # But skip very small windows (likely tooltips or overlays)
                        if ww < 50 or wh < 50:
                            continue
                        return True
                else:
                    # Fallback: assume the first window of target app we hit is our target.
                    return False
            else:
                # Another app's window is in front. 
                # Ignore very small windows (likely tooltips or overlays)
                if ww < 50 or wh < 50:
                    continue
                if layer == 0:
                    return True

    return False


def get_clickable_elements(pid: int) -> List[Dict[str, Any]]:
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
        wid = get_window_id(el["element"])
        if _is_element_covered(ex, ey, ew, eh, pid, win_list, target_wid=wid):
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
    seen_centers: List[Tuple[float, float]] = []
    
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


def get_all_clickable_elements(pid_bounds_map: Dict[int, List[Tuple[float, float, float, float]]]) -> List[Dict[str, Any]]:
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
            wid = get_window_id(el["element"])
            if _is_element_covered(ex, ey, ew, eh, pid, win_list, target_wid=wid):
                continue

            visible.append(_enrich_element(el))
            
        # Spatial Deduplication
        visible.sort(key=lambda x: (
            not x.get("is_direct", False),
            x["role"] not in ALWAYS_CLICKABLE
        ))
        
        seen_centers: List[Tuple[float, float]] = []
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


def search(query: str, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


def _score_element(el: Dict[str, Any], query_lower: str, semantic: Optional[Tuple[str, str]]) -> int:
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


def _subsequence_match(query: str, text: str) -> bool:
    """Check if all chars in query appear in text in order (case-insensitive)."""
    it = iter(text.lower())
    return all(c.lower() in it for c in query)
