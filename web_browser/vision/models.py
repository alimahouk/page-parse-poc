from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageAnalysisResult:
    """Results from image analysis."""
    caption: Optional[str]
    detected_text: Optional[str]
    accessibility_description: Optional[str] = None