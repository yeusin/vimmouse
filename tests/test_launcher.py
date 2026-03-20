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
    mock_search_field.stringValue.return_value = "rminal"
    launcher._search_field = mock_search_field
    
    launcher._row_views = [MagicMock() for _ in range(9)]
    
    # Simulate query change
    launcher._on_query_changed()
    
    # 'rminal' should fuzzy match Terminal but NOT as a prefix, so show "Search Google" at top
    assert len(launcher._results) == 2
    assert launcher._results[0][1] == "web:rminal"
    assert launcher._results[1][0] == "Terminal"
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


def test_launcher_reposition_on_show(mocker):
    from AppKit import NSScreen, NSMakeRect
    launcher = Launcher()
    
    # 1. First show - window is built
    screen1 = MagicMock()
    screen1.size.width = 1920.0
    screen1.size.height = 1080.0
    screen1.origin.x = 0.0
    screen1.origin.y = 0.0
    mocker.patch.object(NSScreen, "mainScreen", return_value=MagicMock(frame=lambda: screen1))
    
    # Mocking _scan_apps and other things needed for show()
    launcher._app_cache = []
    
    # Mocking _build_window to just create a mock window
    mock_window = MagicMock()
    launcher._window = mock_window
    launcher._search_field = MagicMock()
    
    # 2. Change screen size and show again
    screen2 = MagicMock()
    screen2.size.width = 2560.0
    screen2.size.height = 1440.0
    screen2.origin.x = 100.0  # Test non-zero origin too
    screen2.origin.y = 50.0
    mocker.patch.object(NSScreen, "mainScreen", return_value=MagicMock(frame=lambda: screen2))
    
    launcher.show()
    
    # Verify setFrame_display_ was called with new coordinates
    # _WIN_W = 620, _WIN_H = 460
    # x = 100 + (2560 - 620) / 2 = 100 + 970 = 1070
    # y = 50 + (1440 - 460) / 2 + 1440 * 0.1 = 50 + 490 + 144 = 684
    
    # We expect setFrame_display_ to be called
    mock_window.setFrame_display_.assert_called()
    args, _ = mock_window.setFrame_display_.call_args
    rect = args[0]
    assert rect.origin.x == 1070.0
    assert rect.origin.y == 684.0


def test_launcher_web_search(mocker):
    launcher = Launcher()
    launcher._app_cache = [("Safari", "/Applications/Safari.app")]
    launcher._row_views = [MagicMock() for _ in range(9)]
    mock_search_field = MagicMock()
    launcher._search_field = mock_search_field

    # 1. Query with no exact match
    mock_search_field.stringValue.return_value = "google"
    launcher._on_query_changed()
    
    # Should have "Search Google" result
    assert len(launcher._results) == 1
    assert launcher._results[0][0] == 'Search Google for "google"'
    assert launcher._results[0][1] == "web:google"

    # 2. Query with prefix match
    mock_search_field.stringValue.return_value = "Saf"
    launcher._on_query_changed()
    
    # Should have both "Safari" and "Search Google", with Safari at the top
    assert len(launcher._results) == 2
    assert launcher._results[0][0] == "Safari"
    assert launcher._results[1][1] == "web:Saf"

    # 3. Launch web search
    launcher._results = [('Search Google for "google"', "web:google")]
    launcher._selected = 0
    launcher._window = MagicMock()
    mock_workspace = mocker.patch("vimlayer.launcher.NSWorkspace.sharedWorkspace")
    mock_url_class = mocker.patch("vimlayer.launcher.NSURL")
    
    launcher._launch_selected()
    
    # Verify it opened a google search URL
    mock_url_class.URLWithString_.assert_called()
    args = mock_url_class.URLWithString_.call_args[0]
    assert "google.com/search?q=google" in args[0]
    mock_workspace.return_value.openURL_.assert_called()


def test_launcher_selection_memory(mocker, tmp_path):
    # Mock memory path to use a temp file
    mem_file = tmp_path / "launcher_memory.json"
    mocker.patch("vimlayer.launcher._MEMORY_PATH", str(mem_file))
    
    launcher = Launcher()
    launcher._app_cache = [
        ("Safari", "/Applications/Safari.app"),
        ("Terminal", "/Applications/Utilities/Terminal.app"),
    ]
    launcher._row_views = [MagicMock() for _ in range(9)]
    mock_search_field = MagicMock()
    launcher._search_field = mock_search_field
    
    # 1. Search for "t", Terminal is a prefix match, so it's on top
    mock_search_field.stringValue.return_value = "t"
    launcher._on_query_changed()
    assert launcher._results[0][0] == "Terminal"
    
    # 2. Search for "t", move selection to Web Search (index 1) and launch it
    # Prefix: Terminal, Index 1: Search Google for "t", Index 2: Safari (fuzzy)
    assert launcher._results[1][1] == "web:t"
    launcher._selected = 1
    launcher._window = MagicMock()
    mocker.patch("vimlayer.launcher.NSWorkspace.sharedWorkspace")
    launcher._launch_selected()
    
    # 3. Search for "t" again - Web Search should now be on top because it was selected
    launcher._on_query_changed()
    assert launcher._results[0][1] == "web:t"
    assert launcher._results[1][0] == "Terminal"
    
    # 4. Search for "Sa", select Safari and launch it 5 times
    mock_search_field.stringValue.return_value = "Sa"
    launcher._on_query_changed()
    # Results for "Sa": [('Safari', 0), ('Search Google for "Sa"', 0)]
    assert launcher._results[0][0] == "Safari"
    
    launcher._selected = 0 # Safari
    for _ in range(5):
        launcher._launch_selected()
    
    # 5. Search for "Sa" - Safari should still be on top
    launcher._on_query_changed()
    assert launcher._results[0][0] == "Safari"
    
    # 6. Now search for "Te", select "Terminal" (prefix) 10 times
    mock_search_field.stringValue.return_value = "Te"
    launcher._on_query_changed()
    # Terminal is prefix, should be index 0
    assert launcher._results[0][0] == "Terminal"
    launcher._selected = 0
    for _ in range(10):
        launcher._launch_selected()
        
    # 7. Search for "Te" again - Terminal should still be on top
    launcher._on_query_changed()
    assert launcher._results[0][0] == "Terminal"

    # 8. Test fuzzy match jumping to top
    # Search for "a" (Terminal is fuzzy, Safari is prefix)
    mock_search_field.stringValue.return_value = "a"
    # Select Terminal 20 times for "a"
    # First find where Terminal is for "a"
    launcher._on_query_changed()
    term_idx = -1
    for i, res in enumerate(launcher._results):
        if res[0] == "Terminal":
            term_idx = i
            break
    assert term_idx != -1
    
    launcher._selected = term_idx
    for _ in range(20):
        launcher._launch_selected()
    
    # Now Terminal should be #1 for query "a"
    launcher._on_query_changed()
    assert launcher._results[0][0] == "Terminal"
