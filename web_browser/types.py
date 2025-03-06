from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class HistoryEntry:
    """Represents a single browsing history entry"""

    timestamp: datetime
    url: str
    screenshot_path: Optional[str] = None
    title: Optional[str] = None
