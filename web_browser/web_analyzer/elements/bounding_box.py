"""
Module for handling element bounding boxes and geometric operations.
"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image
from selenium.webdriver.remote.webdriver import WebDriver


@dataclass
class BoundingBox:
    """
    Represents a geometric bounding box for web elements with conversion
    and comparison capabilities.
    
    Attributes:
        left: X-coordinate of left edge
        top: Y-coordinate of top edge
        right: X-coordinate of right edge
        bottom: Y-coordinate of bottom edge
        width: Width of bounding box
        height: Height of bounding box
    """
    left: float
    top: float
    right: float = 0.0
    bottom: float = 0.0
    width: float = 0.0
    height: float = 0.0

    def calculate_overlap(self, other: 'BoundingBox') -> float:
        """
        Calculate overlap ratio between this and another bounding box.
        
        Args:
            other: BoundingBox to compare with
            
        Returns:
            Float between 0 and 1 representing overlap ratio
        """
        x_left = max(self.left, other.left)
        y_top = max(self.top, other.top)
        x_right = min(self.right, other.right)
        y_bottom = min(self.bottom, other.bottom)
        
        if x_right <= x_left or y_bottom <= y_top:
            return 0.0
            
        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        self_area = self.width * self.height
        other_area = other.width * other.height
        smaller_area = min(self_area, other_area)
        
        return intersection_area / smaller_area if smaller_area > 0 else 0.0
    
    @classmethod
    def from_dom_position(cls, position: dict) -> "BoundingBox":
        """
        Create a BoundingBox from DOM element position data.
        
        Args:
            position: Dictionary containing x, y, width, height coordinates
            
        Returns:
            BoundingBox instance
        """
        x = float(position.get("x", 0))
        y = float(position.get("y", 0))
        width = float(position.get("width", 0))
        height = float(position.get("height", 0))
        
        return cls(
            left=x,
            top=y,
            width=width,
            height=height,
            right=x + width,
            bottom=y + height
        )
    
    @classmethod
    def from_polygon(cls, polygon: list[float], driver: WebDriver) -> "BoundingBox":
        """
        Create a BoundingBox from OCR polygon points.
        
        Args:
            polygon: List of x,y coordinates forming polygon vertices
            driver: WebDriver instance for scaling calculations
            
        Returns:
            BoundingBox instance
            
        Raises:
            ValueError: If polygon has fewer than 4 points
        """
        if len(polygon) < 8:
            raise ValueError("Polygon must have at least 4 points (8 coordinates)")
        
        scale_x, scale_y = cls._get_scale_factors(driver)
        
        x_coords = [x / scale_x for x in polygon[::2]]
        y_coords = [y / scale_y for y in polygon[1::2]]
        
        left = min(x_coords)
        top = min(y_coords)
        right = max(x_coords)
        bottom = max(y_coords)
        
        return cls(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            width=right - left,
            height=bottom - top
        )
    
    @classmethod
    def from_rectangle(cls, rect: dict) -> "BoundingBox":
        """
        Create a BoundingBox from a rectangle dictionary.
        
        Args:
            rect: Dictionary containing left, top, width, height coordinates
            
        Returns:
            BoundingBox instance
        """
        left = rect["left"]
        top = rect["top"]
        width = rect.get("width", 0)
        height = rect.get("height", 0)
        
        return cls(
            left=left,
            top=top,
            right=left + width,
            bottom=top + height,
            width=width,
            height=height
        )
    
    @staticmethod
    def _get_scale_factors(driver: WebDriver) -> tuple[float, float]:
        """
        Calculate scale factors between screenshot and viewport dimensions.
        
        Args:
            driver: WebDriver instance
            
        Returns:
            Tuple of (x_scale, y_scale) factors
        """
        viewport_width = driver.execute_script("return window.innerWidth")
        viewport_height = driver.execute_script("return window.innerHeight")
        
        screenshot = Image.open(BytesIO(driver.get_screenshot_as_png()))
        screenshot_width, screenshot_height = screenshot.size
        
        return (
            screenshot_width / viewport_width,
            screenshot_height / viewport_height
        )
    
    def is_almost_equal(self, other: "BoundingBox", tolerance: float = 1.0) -> bool:
        """
        Check if two bounding boxes are approximately equal within tolerance.
        
        Args:
            other: BoundingBox to compare with
            tolerance: Maximum allowed difference in coordinates
            
        Returns:
            True if boxes are approximately equal
        """
        return (
            abs(self.left - other.left) <= tolerance and
            abs(self.top - other.top) <= tolerance and
            abs(self.right - other.right) <= tolerance and
            abs(self.bottom - other.bottom) <= tolerance
        )
    
    def merge_with(self, other: "BoundingBox") -> "BoundingBox":
        """
        Create a new BoundingBox that encompasses both boxes.
        
        Args:
            other: BoundingBox to merge with
            
        Returns:
            New BoundingBox containing both boxes
        """
        left = min(self.left, other.left)
        top = min(self.top, other.top)
        right = max(self.right, other.right)
        bottom = max(self.bottom, other.bottom)
        
        return BoundingBox(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            width=right - left,
            height=bottom - top
        )