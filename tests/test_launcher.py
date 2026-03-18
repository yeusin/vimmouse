import sys
from unittest.mock import MagicMock
import pytest
from vimlayer.launcher import _fuzzy_match, _fuzzy_score, _scan_apps, Launcher


def test_fuzzy_match():
    # Exact match
    assert _fuzzy_match("chrome", "Google Chrome")
    # Subsequence match
    assert _fuzzy_match("gch", "Google Chrome")
    # Case insensitive
    assert _fuzzy_match("CHROME", "Google Chrome")
    # Non-match
    assert not _fuzzy_match("xyz", "Google Chrome")
    # Empty query matches everything
    assert _fuzzy_match("", "Anything")


def test_fuzzy_score():
    # Lower score is better
    # Prefix match should be better than subsequence
    score_prefix = _fuzzy_score("term", "Terminal")
    score_subseq = _fuzzy_score("term", "iTerm")
    assert score_prefix < score_subseq

    # Word boundary match should be better than mid-word match
    score_boundary = _fuzzy_score("gc", "Google Chrome")
    score_midword = _fuzzy_score("gc", "MagicCity")
    assert score_boundary < score_midword


def test_scan_apps(mocker):
    # Mock os.path.isdir and os.listdir
    def mock_isdir(path):
        return path in [
            "/Applications",
            "/System/Applications",
            "/System/Library/PreferencePanes"
        ]

    def mock_listdir(path):
        if path == "/Applications":
            return ["Safari.app", "Utilities"]
        elif path == "/Applications/Utilities":
            return ["Terminal.app", "Activity Monitor.app"]
        elif path == "/System/Applications":
            return ["Calculator.app"]
        elif path == "/System/Library/PreferencePanes":
            return ["Displays.prefPane", "Network.prefPane"]
        return []

    mocker.patch("os.path.isdir", side_effect=mock_isdir)
    mocker.patch("os.listdir", side_effect=mock_listdir)
    mocker.patch("os.path.expanduser", return_value="/Users/test/Applications")

    apps = _scan_apps()
    
    # Should find apps in /Applications
    assert ("Safari", "/Applications/Safari.app") in apps
    # Should NOT find Utilities directly (it's a dir, not .app)
    # The scan_apps only goes one level deep into subdirectories for apps
    # Oh wait, `_scan_apps` implementation:
    # elif os.path.isdir(full): ... listdir(full) ... sub.endswith(".app")
    # The mock for os.path.isdir needs to return True for /Applications/Utilities
    
    # Wait, my mock_isdir only allows specific paths. Let's fix mock_isdir to allow /Applications/Utilities
    pass

def test_scan_apps_fixed(mocker):
    def mock_isdir(path):
        return path in [
            "/Applications",
            "/Applications/Utilities",
            "/System/Applications",
            "/System/Library/PreferencePanes",
            "/System/Library/CoreServices/Finder.app"
        ]

    def mock_listdir(path):
        if path == "/Applications":
            return ["Safari.app", "Utilities", "NotAnApp.txt"]
        elif path == "/Applications/Utilities":
            return ["Terminal.app"]
        elif path == "/System/Applications":
            return ["Calculator.app"]
        elif path == "/System/Library/PreferencePanes":
            return ["Displays.prefPane"]
        return []

    mocker.patch("os.path.isdir", side_effect=mock_isdir)
    mocker.patch("os.listdir", side_effect=mock_listdir)
    mocker.patch("os.path.expanduser", return_value="/Users/test/Applications")

    apps = _scan_apps()

    # Assert sorted order by name
    names = [name for name, path in apps]
    assert names == ["Calculator", "Displays", "Finder", "Safari", "Terminal"]

    assert ("Calculator", "/System/Applications/Calculator.app") in apps
    assert ("Displays", "/System/Library/PreferencePanes/Displays.prefPane") in apps
    assert ("Finder", "/System/Library/CoreServices/Finder.app") in apps
    assert ("Safari", "/Applications/Safari.app") in apps
    assert ("Terminal", "/Applications/Utilities/Terminal.app") in apps


def test_launcher_state(mocker):
    launcher = Launcher()
    
    # Mocking app cache to avoid file system scan
    launcher._app_cache = [
        ("Activity Monitor", "/System/Applications/Utilities/Activity Monitor.app"),
        ("Google Chrome", "/Applications/Google Chrome.app"),
        ("Safari", "/Applications/Safari.app"),
        ("Terminal", "/Applications/Utilities/Terminal.app"),
    ]
    
    # Mock search field and row views
    mock_search_field = MagicMock()
    mock_search_field.stringValue.return_value = "term"
    launcher._search_field = mock_search_field
    
    launcher._row_views = [MagicMock() for _ in range(9)]
    
    # Simulate query change
    launcher._on_query_changed()
    
    # 'term' should match Terminal
    assert len(launcher._results) == 1
    assert launcher._results[0][0] == "Terminal"
    assert launcher._selected == 0
    
    # Test selection moving
    launcher._results = launcher._app_cache # Reset to all 4 items
    launcher._selected = 0
    
    # Move down
    launcher._move_selection(1)
    assert launcher._selected == 1
    
    # Move down beyond bounds
    launcher._move_selection(10)
    assert launcher._selected == 3
    
    # Move up
    launcher._move_selection(-1)
    assert launcher._selected == 2
    
    # Move up beyond bounds
    launcher._move_selection(-10)
    assert launcher._selected == 0
