"""AX tree querying (platform-agnostic wrapper)."""

from typing import Any, Dict, List, Optional, Tuple
from .platforms import get_platform


def is_input_element(element: Any) -> bool:
    return get_platform().accessibility.is_input_element(element)


def get_focused_element() -> Optional[Any]:
    return get_platform().accessibility.get_focused_element()


def get_element_pid(element: Any) -> Optional[int]:
    return get_platform().accessibility.get_element_pid(element)


def is_element_stale(element: Any) -> bool:
    return get_platform().accessibility.is_element_stale(element)


def get_clickable_elements(pid: int) -> List[Dict[str, Any]]:
    return get_platform().accessibility.get_clickable_elements(pid)


def get_all_clickable_elements(
    pid_bounds_map: Dict[int, List[Tuple[float, float, float, float]]],
) -> List[Dict[str, Any]]:
    return get_platform().accessibility.get_all_clickable_elements(pid_bounds_map)
