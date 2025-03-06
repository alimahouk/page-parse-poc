from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class FigureInfo:
    """Represents information about a figure in the document."""
    page_number: int
    polygon: list[float]
    spans: list[Any]


@dataclass
class OCRElement:
    """Represents a single word or text element from OCR analysis."""
    confidence: float
    content: str
    polygon: list[float]
    page_number: Optional[int] = None
    span: Optional[Any] = None


@dataclass
class OCRLine:
    """Represents a line of text from OCR, which may contain multiple words."""
    confidence: float
    content: str
    polygon: list[float]
    words: list[tuple[str, float]]
    page_number: Optional[int] = None


@dataclass
class TableInfo:
    """Represents information about a table in the document."""
    cells: list[dict[str, Any]]
    column_count: int
    page_number: int
    polygon: list[float]
    row_count: int