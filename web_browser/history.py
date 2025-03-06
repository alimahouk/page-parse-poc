from typing import Optional

from web_browser.types import HistoryEntry


class BrowserHistory:
    """Manages browser history with support for navigation"""

    def __init__(self):
        self._history: list[HistoryEntry] = []
        self._current_index: int = -1

    def add_entry(self, entry: HistoryEntry) -> None:
        """Add a new history entry and update the current index"""
        # If we're not at the end of history, remove all future entries
        if self._current_index < len(self._history) - 1:
            self._history = self._history[: self._current_index + 1]

        self._history.append(entry)
        self._current_index = len(self._history) - 1

    def can_go_back(self) -> bool:
        """Check if we can navigate backwards"""
        return self._current_index > 0

    def can_go_forward(self) -> bool:
        """Check if we can navigate forwards"""
        return self._current_index < len(self._history) - 1

    def get_current(self) -> Optional[HistoryEntry]:
        """Get current history entry"""
        if 0 <= self._current_index < len(self._history):
            return self._history[self._current_index]
        return None

    def get_history(self) -> list[HistoryEntry]:
        """Get all history entries"""
        return self._history.copy()

    def go_back(self) -> Optional[HistoryEntry]:
        """Navigate to previous entry"""
        if self.can_go_back():
            self._current_index -= 1
            return self._history[self._current_index]
        return None

    def go_forward(self) -> Optional[HistoryEntry]:
        """Navigate to next entry"""
        if self.can_go_forward():
            self._current_index += 1
            return self._history[self._current_index]
        return None

    def update_current(self, entry: HistoryEntry) -> None:
        """Update the current history entry with new data"""
        if 0 <= self._current_index < len(self._history):
            self._history[self._current_index] = entry
