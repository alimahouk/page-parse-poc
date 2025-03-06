"""Manager for handling element styles and computations."""

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from web_browser.web_analyzer.utils import js


class StyleManager:
    """Manages element styles and computations."""
    
    def compare_styles(
        self,
        before_styles: dict[str, str],
        after_styles: dict[str, str]
    ) -> dict[str, tuple[str, str]]:
        """
        Compare two sets of styles and return the differences.
        
        Returns:
            Dict[str, Tuple[str, str]]: Dictionary of changed properties with their before/after values
        """
        changes = {}
        for key in before_styles:
            if key in after_styles and before_styles[key] != after_styles[key]:
                changes[key] = (before_styles[key], after_styles[key])
        return changes
    
    @staticmethod
    def get_computed_styles(driver: WebDriver, element: WebElement) -> dict[str, str]:
        """Get relevant computed styles for an element."""
        return js.get_computed_styles(driver, element)
    
    def get_element_colors(
        self,
        driver: WebDriver,
        element: WebElement
    ) -> dict[str, str]:
        """
        Get element's color-related styles.
        
        Returns:
            Dict[str, str]: Dictionary with color, backgroundColor, and borderColor
        """
        styles = self.get_computed_styles(driver, element)
        return {
            "color": styles.get("color", ""),
            "backgroundColor": styles.get("backgroundColor", ""),
            "borderColor": styles.get("borderColor", "")
        }
    
    def get_element_dimensions(
        self, 
        driver: WebDriver, 
        element: WebElement
    ) -> tuple[float, float]:
        """
        Get element's width and height from computed styles.
        
        Returns:
            Tuple[float, float]: (width, height) in pixels
        """
        styles = self.get_computed_styles(driver, element)
        return (
            self.parse_css_dimension(styles.get("width", "0")),
            self.parse_css_dimension(styles.get("height", "0"))
        )
    
    def get_element_opacity(
        self, 
        driver: WebDriver, 
        element: WebElement
    ) -> float:
        """
        Get element's opacity from computed styles.
        
        Returns:
            float: Opacity value between 0 and 1
        """
        styles = self.get_computed_styles(driver, element)
        try:
            return max(0.0, min(1.0, float(styles.get("opacity", 1))))
        except (ValueError, TypeError):
            return 1.0
    
    def is_element_visible(self, driver: WebDriver, element: WebElement) -> bool:
        """Check if an element is visible based on its computed styles."""
        styles = self.get_computed_styles(driver, element)
        return (
            styles.get("display") != "none" and
            styles.get("visibility") != "hidden" and
            styles.get("opacity") != "0"
        )

    @staticmethod
    def parse_css_dimension(value: str) -> float:
        """
        Safely parse a CSS dimension value to float.
        Handles 'auto', percentage values, and other non-pixel units.
        
        Args:
            value: CSS dimension value as string
            
        Returns:
            float: Parsed numeric value, or 0 if parsing fails
        """
        if not value or value == "auto":
            return 0.0
        
        try:
            # Remove common CSS units.
            for unit in ["px", "em", "rem", "%", "vh", "vw", "pt"]:
                if value.endswith(unit):
                    value = value.rstrip(unit)
                    break
            return float(value)
        except (ValueError, TypeError):
            return 0.0