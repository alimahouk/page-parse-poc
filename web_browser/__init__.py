import json
import logging
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from web_browser.document_intelligence.client import DocumentClient
from web_browser.document_intelligence.config import ProcessingConfig
from web_browser.document_intelligence.processor import DocumentProcessor
from web_browser.dom.builder import DOMTreeBuilder
from web_browser.dom.models import DOMTree
from web_browser.driver import new_webdriver
from web_browser.history import BrowserHistory
from web_browser.types import HistoryEntry
from web_browser.vision.client import VisionAnalysisClient
from web_browser.vision.types import (ImageElement, InteractiveElement,
                                      WebpageDescription)
from web_browser.web_analyzer.analyzer import ElementAnalyzer
from web_browser.web_analyzer.config import Config
from web_browser.web_analyzer.elements.merger import ElementMerger
from web_browser.web_analyzer.elements.unified_element import UnifiedElement
from web_browser.web_analyzer.utils import js

logger = logging.getLogger(__name__)


class WebBrowser:
    def __init__(
        self,
        headless: bool = True,
        screenshot_dir: str = "ui",
        parse_delay: float = 30,
        overlap_threshold: float = 0.5,
    ) -> None:
        """
        Initialize the WebBrowser instance.

        Args:
            screenshot_dir: Directory to store screenshots
            parse_delay: Delay in seconds to wait for page load
            overlap_threshold: Threshold for element overlap matching
        """
        self.driver: WebDriver = None
        self.headless: bool = headless
        self.history: BrowserHistory = BrowserHistory()
        self.parse_delay: float = parse_delay
        self.overlap_threshold: float = overlap_threshold
        self.screenshot_dir: Path = Path(screenshot_dir)

        self.screenshot_dir.mkdir(exist_ok=True)
        self._setup_driver()

    def __enter__(self):
        """Support for context manager protocol."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Ensure browser is closed when exiting context."""
        self.close()

    def analyze_hover_for_elements(
        self, 
        elements: list[UnifiedElement],
        criteria: Optional[list[dict]] = None
    ) -> dict[str, dict]:
        """
        Analyze hover changes for specific elements or elements matching criteria.

        Args:
            elements: List of UnifiedElements to potentially analyze
            criteria: Optional list of criteria dicts to filter elements.
                     If None, analyzes all provided elements.

        Returns:
            dict[str, dict]: Dictionary mapping element selectors to their hover changes
        """
        config = Config(
            screenshot_dir=str(self.screenshot_dir),
            parse_delay=0,
            viewport_only=True
        )
        analyzer = ElementAnalyzer(config)
        
        hover_changes = {}
        
        for element in elements:
            if not element.selector:
                continue
                
            if criteria and not any(self._element_matches_criteria(element, c) for c in criteria):
                continue
                
            try:
                web_element = self.driver.find_element("css selector", element.selector)
            except Exception:
                continue
                
            temp_element = {
                "element": web_element,
                "tag": element.tag or "",
                "text": element.content or "",
                "rect": {
                    "left": element.bounding_box.left,
                    "top": element.bounding_box.top,
                    "width": element.bounding_box.width,
                    "height": element.bounding_box.height
                }
            }
            
            hover_data = analyzer.capture_hover_state(self.driver, temp_element, 0)
            if hover_data:
                changes = analyzer._analyze_hover_data(hover_data)
                if changes:
                    hover_changes[element.selector] = changes
                    
        return hover_changes
    
    def _build_dom(self) -> DOMTree:
        """Build and return the DOM tree for the current page."""
        builder = DOMTreeBuilder(self.driver)
        return builder.build_tree()

    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def _element_matches_criteria(self, element: UnifiedElement, criteria: dict) -> bool:
        """Check if an element matches the given criteria."""
        if "tag" in criteria and criteria["tag"].lower() != (element.tag or "").lower():
            return False
            
        if "class" in criteria and criteria["class"] not in (element.class_name or ""):
            return False
            
        if "id" in criteria and criteria["id"] != element.id:
            return False
            
        if "text" in criteria and criteria["text"] not in (element.content or ""):
            return False
            
        return True
    
    def get_current_url(self) -> Optional[str]:
        """Get current URL from history"""
        entry = self.history.get_current()
        return entry.url if entry else None

    def get_element_screenshot(
        self, element: UnifiedElement, padding: int = 70
    ) -> Optional[Image.Image]:
        """
        Capture a screenshot of a specific UnifiedElement with padding around it.

        Args:
            element: UnifiedElement to capture
            padding: Number of pixels to add around the element (default: 20)

        Returns:
            PIL.Image.Image or None: Screenshot of the element region if successful
        """
        if not element or not element.bounding_box:
            return None

        # Take viewport screenshot
        screenshot_bytes = self.driver.get_screenshot_as_png()
        viewport_screenshot = Image.open(BytesIO(screenshot_bytes))

        # Get device pixel ratio for scaling
        dpr = self.driver.execute_script("return window.devicePixelRatio || 1")

        # Scale coordinates by device pixel ratio
        left = max(0, int(element.bounding_box.left * dpr) - padding)
        top = max(0, int(element.bounding_box.top * dpr) - padding)
        right = min(
            viewport_screenshot.width,
            int((element.bounding_box.left + element.bounding_box.width) * dpr)
            + padding,
        )
        bottom = min(
            viewport_screenshot.height,
            int((element.bounding_box.top + element.bounding_box.height) * dpr)
            + padding,
        )

        # Ensure coordinates are valid
        if left >= right or top >= bottom:
            return None

        # Crop and return
        return viewport_screenshot.crop((left, top, right, bottom))

    def get_history_entries(self) -> list[HistoryEntry]:
        """Get all history entries"""
        return self.history.get_history()

    def get_page_description(self) -> WebpageDescription:
        """
        Get an accessibility description of the current page.

        Returns:
            str: Description of the page content
        """
        viewport_filename = self.screenshot_dir / "viewport.jpg"
        self._save_screenshot(
            self.driver.get_screenshot_as_png(),
            viewport_filename
        )

        vision_client = VisionAnalysisClient.from_env()
        return vision_client.describe_screenshot(str(viewport_filename))

    def get_unified_elements(self, detect_hover_for: Optional[list[dict]] = None) -> list[UnifiedElement]:
        """
        Get both OCR and clickable elements merged into a unified format.

        Args:
            detect_hover_for: Optional list of element criteria to detect hover changes for.
                            Each dict should contain criteria like:
                            {
                                'tag': str,  # HTML tag name
                                'class': str,  # CSS class
                                'id': str,    # Element ID
                                'text': str   # Element text content
                            }
                            All specified criteria in a dict must match for hover to be detected.

        Returns:
            List[UnifiedElement]: List of unified elements combining OCR and clickable elements
        """
        viewport_filename = self.screenshot_dir / "viewport.jpg"

        config = Config(
            screenshot_dir=str(self.screenshot_dir),
            parse_delay=0,
            viewport_only=True
        )
        analyzer = ElementAnalyzer(config)

        clickable_elements = analyzer.analyze_elements(
            self.driver,
            hover_criteria=detect_hover_for
        )

        # Initialize document processing
        client = DocumentClient.from_env()
        processing_config = ProcessingConfig(
            min_confidence=0.8, 
            clean_text=True, 
            debug_output=True
        )
        processor = DocumentProcessor(client, processing_config)

        # Get OCR elements
        ocr_elements = processor.analyze_read(str(viewport_filename))

        # Get DOM elements
        dom_tree = self._build_dom()

        # Merge elements
        merger = ElementMerger(overlap_threshold=self.overlap_threshold)
        return merger.merge_elements(
            ocr_elements=ocr_elements,
            clickable_elements=clickable_elements,
            dom_tree=dom_tree,
            driver=self.driver,
        )

    def go_back(self) -> bool:
        """
        Navigate back in history.

        Returns:
            bool: True if navigation was successful
        """
        entry = self.history.go_back()
        if entry:
            self.driver.get(entry.url)
            self._wait_for_page_load()
            return True
        return False

    def go_forward(self) -> bool:
        """
        Navigate forward in history.

        Returns:
            bool: True if navigation was successful
        """
        entry = self.history.go_forward()
        if entry:
            self.driver.get(entry.url)
            self._wait_for_page_load()
            return True
        return False

    def navigate_to(self, url: str) -> bool:
        """
        Navigate to the specified URL and add it to history.

        Args:
            url: The URL to navigate to

        Returns:
            bool: True if navigation was successful, False otherwise
        """
        try:
            self.driver.get(url)
            self._wait_for_page_load()

            # Get page title
            title = self.driver.title or url

            # Take screenshot for history
            screenshot_path = (
                self.screenshot_dir / f"history_{int(time.time())}.jpg"
            )
            self._save_screenshot(
                self.driver.get_screenshot_as_png(),
                screenshot_path
            )

            # Create and add history entry
            entry = HistoryEntry(
                url=url,
                title=title,
                timestamp=datetime.now(),
                screenshot_path=str(screenshot_path),
            )
            self.history.add_entry(entry)

            return True

        except Exception as e:
            logger.error(f"Navigation failed: {str(e)}")
            return False

    def refresh(self) -> bool:
        """
        Refresh the current page and update its history entry with a new screenshot.

        Returns:
            bool: True if refresh was successful, False otherwise
        """
        current_entry = self.history.get_current()
        if not current_entry:
            logger.error("No current history entry found for refresh")
            return False

        try:
            logger.info(f"Refreshing page at URL: {current_entry.url}")
            self.driver.refresh()

            logger.info(f"Waiting {self.parse_delay}s for page to load...")
            self._wait_for_page_load()

            screenshot_path = (
                self.screenshot_dir / f"history_{int(time.time())}.jpg"
            )
            logger.info(f"Taking new screenshot: {screenshot_path}")
            self._save_screenshot(
                self.driver.get_screenshot_as_png(),
                screenshot_path
            )

            new_title = self.driver.title or current_entry.url
            logger.info(f"Updating history entry with new title: {new_title}")

            new_entry = HistoryEntry(
                url=current_entry.url,
                title=new_title,
                timestamp=datetime.now(),
                screenshot_path=str(screenshot_path),
            )
            self.history.update_current(new_entry)

            logger.info("Page refresh completed successfully")
            return True

        except Exception as e:
            logger.error(f"Page refresh failed: {str(e)}")
            return False

    def _save_screenshot(self, screenshot_bytes: bytes, filepath: Path) -> None:
        """
        Save a screenshot as JPEG with proper RGB conversion.
        
        Args:
            screenshot_bytes: PNG screenshot bytes from webdriver
            filepath: Path where to save the JPEG file
        """
        screenshot = Image.open(BytesIO(screenshot_bytes))
        
        # Convert to RGB if needed
        if screenshot.mode in ("RGBA", "LA"):
            background = Image.new("RGB", screenshot.size, (255, 255, 255))
            background.paste(screenshot, mask=screenshot.split()[-1])
            screenshot = background
            
        screenshot.save(filepath, "JPEG", quality=85)
        
    def save_element_screenshot(
        self,
        element: UnifiedElement,
        filename: Optional[str] = None,
        padding: int = 70,
    ) -> Optional[str]:
        """
        Capture and save a screenshot of a specific UnifiedElement.

        Args:
            element: UnifiedElement to capture
            filename: Optional filename to save the screenshot (default: auto-generated)
            padding: Number of pixels to add around the element (default: 70)

        Returns:
            str or None: Path to the saved screenshot if successful
        """
        element_image = self.get_element_screenshot(element, padding)
        if not element_image:
            return None

        # Generate filename if not provided
        if not filename:
            element_type = element.element_type or "unknown"
            content = element.content or "no_content"
            # Clean content for filename
            content = "".join(
                c for c in content[:30] if c.isalnum() or c in ("_", "-", ".")
            ).rstrip(".")
            filename = f"element_{element_type}_{content}.jpg"

        # Ensure filename has .jpg extension
        if not filename.lower().endswith(".jpg"):
            filename = filename.rsplit(".", 1)[0] + ".jpg"

        # Save to screenshot directory
        output_path = self.screenshot_dir / filename
        
        # Convert to RGB if needed
        if element_image.mode in ("RGBA", "LA"):
            background = Image.new("RGB", element_image.size, (255, 255, 255))
            background.paste(element_image, mask=element_image.split()[-1])
            element_image = background
            
        element_image.save(output_path, "JPEG", quality=85)

        return str(output_path)

    def save_history_to_json(
        self, filename: str = "browser_history.json"
    ) -> None:
        """
        Save browsing history to a JSON file.

        Args:
            filename: Name of the output JSON file
        """
        history_data = [
            {
                "url": entry.url,
                "title": entry.title,
                "timestamp": entry.timestamp.isoformat(),
                "screenshot_path": entry.screenshot_path,
            }
            for entry in self.get_history_entries()
        ]

        output_path = self.screenshot_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2, ensure_ascii=False)

    def save_unified_elements_to_json(
        self,
        elements: list[UnifiedElement],
        filename: str = "unified_elements.json",
    ):
        """
        Save unified elements to a JSON file.

        Args:
            elements: List of UnifiedElement instances
            filename: Name of the output JSON file
        """
        unified_elements_data = [
            serialized
            for elem in elements
            if (serialized := WebBrowser.serialize_unified_element(elem))
            is not None
        ]

        output_path = self.screenshot_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(unified_elements_data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def serialize_unified_element(
        elem: UnifiedElement
    ) -> Optional[dict[str, Any]]:
        """Serialize a UnifiedElement instance to a dictionary."""
        if not elem:
            raise ValueError("Expected a UnifiedElement object")

        # Handle bounding box
        bounding_box_data = None
        if elem.bounding_box:
            bounding_box_data = {
                "left": elem.bounding_box.left,
                "top": elem.bounding_box.top,
                "right": elem.bounding_box.right,
                "bottom": elem.bounding_box.bottom,
                "width": elem.bounding_box.width,
                "height": elem.bounding_box.height,
            }

        # Build dictionary with only non-None values
        element_data = {}

        if elem.content:
            element_data["content"] = elem.content
        if elem.element_type:
            element_data["element_type"] = elem.element_type
        if elem.tag:
            element_data["tag"] = elem.tag
        if elem.confidence is not None:
            element_data["confidence"] = elem.confidence
        if bounding_box_data:
            element_data["bounding_box"] = bounding_box_data
        if elem.screenshots:
            element_data["screenshots"] = elem.screenshots
        if elem.image_caption:
            element_data["image_caption"] = elem.image_caption
        if elem.href:
            element_data["href"] = elem.href
        if elem.src:
            element_data["src"] = elem.src
        if elem.selector:
            element_data["selector"] = elem.selector
        if elem.visibility:
            element_data["visibility"] = elem.visibility
        if elem.dom_text:
            element_data["dom_text"] = elem.dom_text
        if elem.ocr_text:
            element_data["ocr_text"] = elem.ocr_text

        return element_data

    @staticmethod
    def serialize_webpage_description(
        description: WebpageDescription,
    ) -> dict[str, Any]:
        """
        Serialize a WebpageDescription instance to a dictionary.

        Args:
            description: WebpageDescription object to serialize

        Returns:
            Dictionary containing the serialized data

        Raises:
            ValueError: If description is None
        """
        if not description:
            raise ValueError("Expected a WebpageDescription object")

        # Serialize ImageElement objects
        def serialize_image(image: ImageElement) -> dict[str, str]:
            return {
                "location": image.location,
                "content": image.content,
                "purpose": image.purpose,
            }

        # Serialize InteractiveElement objects
        def serialize_interactive(elem: InteractiveElement) -> dict[str, Any]:
            element_data = {
                "type": elem.type,
                "location": elem.location,
                "visuals": elem.visuals,
                "purpose": elem.purpose,
            }
            # Add optional fields only if they exist
            if elem.text:
                element_data["text"] = elem.text
            if elem.state:
                element_data["state"] = elem.state
            return element_data

        # Serialize LayoutSection
        layout_data = {"main_content": description.layout.main_content}
        # Add optional layout fields if they exist
        if description.layout.header:
            layout_data["header"] = description.layout.header
        if description.layout.navigation:
            layout_data["navigation"] = description.layout.navigation
        if description.layout.sidebar:
            layout_data["sidebar"] = description.layout.sidebar

        # Build the complete serialized structure
        return {
            "layout": layout_data,
            "interactive_elements": [
                serialize_interactive(elem)
                for elem in description.interactive_elements
            ],
            "key_content": {
                "headings": description.key_content.headings,
                "main_text_blocks": description.key_content.main_text_blocks,
                "images": [
                    serialize_image(img)
                    for img in description.key_content.images
                ],
            },
            "visual_hierarchy": {
                "primary_focus": description.visual_hierarchy.primary_focus,
                "secondary_elements": description.visual_hierarchy.secondary_elements,
                "background_elements": description.visual_hierarchy.background_elements,
            },
        }

    def _setup_driver(self):
        """Initialize the web driver and set up necessary configurations."""
        self.driver = new_webdriver(self.headless)

    def _wait_for_page_load(self):
        """Wait for the page to fully load."""
        time.sleep(self.parse_delay)
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("return document.readyState")
            == "complete"
        )
        js.init(self.driver)
