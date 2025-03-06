from typing import Optional

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from web_browser.dom.js_scripts import GET_ELEMENT_PROPERTIES_SCRIPT
from web_browser.dom.models import DOMNode, DOMTree, ElementProperties


class DOMTreeBuilder:
    """Builds a structured representation of the DOM tree."""
    
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver
        self._viewport_width: Optional[int] = None
        self._viewport_height: Optional[int] = None

    @property
    def viewport_width(self) -> int:
        """Lazy loading of viewport width."""
        if self._viewport_width is None:
            self._viewport_width = self.driver.execute_script("return window.innerWidth;")
        return self._viewport_width

    @property
    def viewport_height(self) -> int:
        """Lazy loading of viewport height."""
        if self._viewport_height is None:
            self._viewport_height = self.driver.execute_script("return window.innerHeight;")
        return self._viewport_height

    def build_tree(self) -> DOMTree:
        """
        Build complete DOM tree.
        
        Returns:
            DOMTree representing the page structure
            
        Raises:
            WebDriverException: If browser automation fails
        """
        try:
            body = self.driver.find_element("tag name", "body")
            tree = self._process_element(body)
            
            return {
                "type": "root",
                "children": [tree] if tree else []
            }
        except WebDriverException as e:
            raise WebDriverException(f"Failed to build DOM tree: {str(e)}")

    def _get_element_properties(self, element: WebElement) -> Optional[ElementProperties]:
        """
        Extract properties from a DOM element.
        
        Args:
            element: WebElement to analyze
            
        Returns:
            ElementProperties if successful, None if failed
        """
        try:
            props = self.driver.execute_script(GET_ELEMENT_PROPERTIES_SCRIPT, element)
            
            if not props:
                return None
                
            # Ensure all required properties have default values and proper types
            return {
                "tagName": str(props.get("tagName", "")),
                "text": str(props.get("text", "")),
                "href": props.get("href"),
                "src": props.get("src"),
                "position": {
                    "x": int(props.get("position", {}).get("x", 0)),
                    "y": int(props.get("position", {}).get("y", 0)),
                    "width": int(props.get("position", {}).get("width", 0)),
                    "height": int(props.get("position", {}).get("height", 0))
                },
                "visibility": {
                    "display": str(props.get("visibility", {}).get("display", "none")),
                    "visibility": str(props.get("visibility", {}).get("visibility", "hidden")),
                    "opacity": str(props.get("visibility", {}).get("opacity", "0"))
                },
                "selector": str(props.get("selector", ""))
            }
        except Exception as e:
            print(f"Error getting properties: {e}")
            return None

    def _is_element_visible(self, properties: Optional[ElementProperties]) -> bool:
        """
        Check if an element is visible in the viewport.
        
        Args:
            properties: Element properties to check
            
        Returns:
            bool indicating if element is visible
        """
        if not properties:
            return False
            
        vis = properties.get("visibility", {})
        pos = properties.get("position", {})
        
        # Basic display/visibility checks
        if (vis.get("display") == "none" or 
            vis.get("visibility") == "hidden" or
            vis.get("opacity") == "0"):
            return False
            
        # Position checks
        if not all(isinstance(pos.get(k), (int, float)) 
                  for k in ["width", "height", "x", "y"]):
            return False
            
        # Size checks
        if pos.get("width", 0) <= 0 or pos.get("height", 0) <= 0:
            return False
            
        # Viewport checks
        x = pos.get("x", 0)
        y = pos.get("y", 0)
        width = pos.get("width", 0)
        height = pos.get("height", 0)
        
        # Allow slight overflow but catch completely out-of-view elements
        margin = 50  # pixels
        if (x + width < -margin or 
            y + height < -margin or
            x > self.viewport_width + margin or
            y > self.viewport_height + margin):
            return False
            
        return True
    
    def _process_element(self, element: WebElement) -> Optional[DOMNode]:
        """Process a single DOM element and its children."""
        properties = self._get_element_properties(element)
        
        # Skip invalid or invisible elements
        if not properties or not self._is_element_visible(properties):
            return None
            
        # Process children
        children: list[DOMNode] = []
        for child in element.find_elements("xpath", "./child::*"):
            if child_node := self._process_element(child):
                children.append(child_node)
        
        # Clean text content
        text = properties.get("text", "").strip()
        if not text and not children:
            return None
            
        return {
            "properties": properties,
            "children": children
        }