import pytest
from vimlayer import accessibility

def test_subsequence_match():
    assert accessibility._subsequence_match("abc", "apple banana cherry")
    assert accessibility._subsequence_match("save", "Save Document")
    assert not accessibility._subsequence_match("save", "sv")
    assert not accessibility._subsequence_match("xyz", "abcde")

def test_score_element_semantic():
    el = {"role": "AXButton", "subrole": "AXCloseButton", "title": "", "description": "", "value": "", "clickable": True}
    score = accessibility._score_element(el, "close", ("AXButton", "AXCloseButton"))
    assert score == 100

def test_score_element_text():
    el = {"role": "AXButton", "subrole": "", "title": "Save Changes", "description": "", "value": "", "clickable": True}
    
    # Exact match (case-insensitive because query is already lowercased)
    assert accessibility._score_element(el, "save changes", None) >= 90
    # Startswith
    assert accessibility._score_element(el, "save", None) >= 70
    # Substring
    assert accessibility._score_element(el, "changes", None) >= 50
    # Fuzzy
    assert accessibility._score_element(el, "sc", None) >= 20

def test_search():
    elements = [
        {"role": "AXButton", "subrole": "", "title": "Submit", "description": "", "value": "", "clickable": True},
        {"role": "AXButton", "subrole": "", "title": "Cancel", "description": "", "value": "", "clickable": True},
    ]
    
    results = accessibility.search("sub", elements)
    assert len(results) == 1
    assert results[0]["title"] == "Submit"
    
    results = accessibility.search("cel", elements) # fuzzy
    assert len(results) == 1
    assert results[0]["title"] == "Cancel"


def test_is_input_element_new_roles():
    from unittest.mock import MagicMock
    # Mock element
    mock_el = MagicMock()
    
    def get_attr(el, attr, _):
        if attr == "AXRole":
            return 0, el._role
        if attr == "AXSubrole":
            return 0, getattr(el, "_subrole", None)
        return -1, None

    import vimlayer.accessibility as acc
    # Temporarily monkeypatch
    original = acc.AXUIElementCopyAttributeValue
    acc.AXUIElementCopyAttributeValue = get_attr
    try:
        # Test AXTextField
        mock_el._role = "AXTextField"
        assert acc.is_input_element(mock_el) is True
        
        # Test AXSearchField
        mock_el._role = "AXSearchField"
        assert acc.is_input_element(mock_el) is True
        
        # Test AXComboBox
        mock_el._role = "AXComboBox"
        assert acc.is_input_element(mock_el) is True
        
        # Test subrole AXSearchField
        mock_el._role = "AXGroup"
        mock_el._subrole = "AXSearchField"
        assert acc.is_input_element(mock_el) is True
        
        # Test non-input role
        mock_el._role = "AXButton"
        mock_el._subrole = None
        assert acc.is_input_element(mock_el) is False
    finally:
        acc.AXUIElementCopyAttributeValue = original

def test_get_focused_element(mocker):
    mock_sw = mocker.patch("vimlayer.accessibility.AXUIElementCreateSystemWide")
    mock_copy = mocker.patch("vimlayer.accessibility.AXUIElementCopyAttributeValue")
    
    mock_copy.return_value = (0, "mock_element")
    
    el = accessibility.get_focused_element()
    assert el == "mock_element"
    mock_sw.assert_called_once()
