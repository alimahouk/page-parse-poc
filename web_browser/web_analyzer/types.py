from dataclasses import dataclass
from enum import StrEnum
from typing import Optional, TypedDict, Union

from selenium.webdriver.remote.webelement import WebElement


class Rectangle(TypedDict):
    bottom: float
    left: float
    right: float
    top: float


class ClickableElement(TypedDict):
    element: WebElement
    hover_state: Optional["HoverChange"]
    image_caption: Optional[str]
    include: bool
    tag: str
    text: str
    rect: Rectangle


@dataclass
class HoverChange:
    """Represents a change in an element's state when hovered."""
    change_regions: list[tuple[int, int, int, int]]
    color_after: Optional[tuple[int, int, int]] = None
    color_before: Optional[tuple[int, int, int]] = None
    cursor_style: Optional[str] = None
    opacity_after: Optional[float] = None
    opacity_before: Optional[float] = None
    size_after: Optional[tuple[int, int]] = None
    size_before: Optional[tuple[int, int]] = None
    text_after: Optional[str] = None
    text_before: Optional[str] = None


class DOMProperties(TypedDict):
    """Type definition for DOM element properties."""
    href: Optional[str]
    src: Optional[str]
    selector: str
    visibility: dict


class HoverChange(TypedDict):
    """Type definition for element hover state changes."""
    change_regions: list[tuple[int, int, int, int]]  # x1, y1, x2, y2 coordinates
    color_after: Optional[tuple[int, int, int]]
    color_before: Optional[tuple[int, int, int]]  # RGB values
    cursor_style: Optional[str]
    opacity_after: float
    opacity_before: float
    size_after: tuple[float, float]
    size_before: tuple[float, float]  # width, height
    text_after: Optional[str]
    text_before: Optional[str]


class ClickableElement(TypedDict):
    """Type definition for clickable elements."""
    element: WebElement
    tag: str
    text: Optional[str]
    rect: dict[str, float]
    index: int
    hover_state: Optional[HoverChange]
    image_caption: Optional[str]


class PageRegion(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


@dataclass
class RegionBounds:
    left: float
    top: float
    right: float
    bottom: float
    
    @classmethod
    def from_page_dimensions(
        cls,
        page_width: float,
        page_height: float,
        region: Union[PageRegion, set[PageRegion]]
    ) -> "RegionBounds":
        """
        Create region bounds based on page dimensions and desired region(s).
        """
        # Convert single region to set for unified processing
        regions = {region} if isinstance(region, PageRegion) else set(region)
        
        # Initialize with full page
        bounds = cls(
            left=0,
            top=0,
            right=page_width,
            bottom=page_height
        )
        
        # Handle combined regions (e.g., TOP + LEFT = TOP_LEFT)
        if PageRegion.TOP in regions:
            bounds.bottom = page_height * 0.33
        if PageRegion.BOTTOM in regions:
            bounds.top = page_height * 0.67
        if PageRegion.LEFT in regions:
            bounds.right = page_width * 0.33
        if PageRegion.RIGHT in regions:
            bounds.left = page_width * 0.67
        if PageRegion.CENTER in regions:
            bounds.left = page_width * 0.33
            bounds.right = page_width * 0.67
            bounds.top = page_height * 0.33
            bounds.bottom = page_height * 0.67
            
        # Handle predefined combinations
        if PageRegion.TOP_LEFT in regions:
            bounds.right = page_width * 0.33
            bounds.bottom = page_height * 0.33
        elif PageRegion.TOP_RIGHT in regions:
            bounds.left = page_width * 0.67
            bounds.bottom = page_height * 0.33
        elif PageRegion.BOTTOM_LEFT in regions:
            bounds.right = page_width * 0.33
            bounds.top = page_height * 0.67
        elif PageRegion.BOTTOM_RIGHT in regions:
            bounds.left = page_width * 0.67
            bounds.top = page_height * 0.67
            
        return bounds