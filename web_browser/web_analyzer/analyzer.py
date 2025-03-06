import hashlib
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from PIL import Image
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from web_browser.vision.client import VisionAnalysisClient
from web_browser.web_analyzer.config import Config
from web_browser.web_analyzer.managers.image import ImageProcessor
from web_browser.web_analyzer.managers.scroll import ScrollManager
from web_browser.web_analyzer.managers.style import StyleManager
from web_browser.web_analyzer.types import ClickableElement, HoverChange
from web_browser.web_analyzer.utils import js
from web_browser.web_analyzer.utils.decorators import error_handler

logger = logging.getLogger(__name__)


class ElementAnalyzer:
    """Main class for analyzing web elements."""
    
    def __init__(self, config: Config = Config(), debug: bool = False, max_workers: int = 5):
        self.config: Config = config
        self.debug: bool = debug
        self._element_cache: dict[str, Any] = {}
        self.image_processor: ImageProcessor = ImageProcessor()
        self.max_workers: int = max_workers
        self.scroll_manager: ScrollManager = ScrollManager()
        self.style_manager: StyleManager = StyleManager()
        self.vision_client: VisionAnalysisClient = VisionAnalysisClient.from_env()
    
    def _analyze_changed_regions(
        self,
        change_regions: list[tuple[int, int, int, int]],
        after_img: np.ndarray
    ) -> list[str]:
        """Analyze text in changed regions."""
        changed_region_texts = []
        
        for (x1, y1, x2, y2) in change_regions:
            region_crop = after_img[y1:y2, x1:x2]
            
            if not self._is_valid_region_size(region_crop.shape[1], region_crop.shape[0]):
                continue
                
            text = self._analyze_region(region_crop, x1, y1, x2, y2)
            if text:
                changed_region_texts.append(text)
                
        return changed_region_texts
    
    @error_handler
    def analyze_elements(
        self, 
        driver: WebDriver,
        hover_criteria: Optional[list[dict]] = None
    ) -> list[dict]:
        """
        Analyze clickable elements with selective hover detection.
        
        Args:
            driver: WebDriver instance
            hover_criteria: Optional list of criteria dicts for hover detection.
                          Each dict can contain 'tag', 'class', 'id', and/or 'text' keys.
        """
        self.setup_screenshot_dir()
        self._save_viewport_screenshot(driver)
        elements = self.get_clickable_elements(driver)
        return self._process_elements(driver, elements, hover_criteria)
    
    @error_handler
    def analyze_element_data(self, data: dict) -> Optional[dict]:
        """Analyze captured element data without viewport operations."""
        try:
            element = data["element"]

            # Analyze screenshot if available
            if data["screenshot"] and not element["text"]:
                self._analyze_element_image(element, data["screenshot"])

            # Analyze hover data if available
            if data["hover_data"]:
                hover_result = self._analyze_hover_data(data["hover_data"])
                if hover_result:
                    element["hover_state"] = hover_result

            # Cache the processed element
            element_hash = self._get_element_hash(element)
            self._element_cache[element_hash] = {
                k: v for k, v in element.items() 
                if k not in {"element"}  # Don't cache WebElement
            }

            return element

        except Exception as e:
            # Keep idx in error logging since it's useful for debugging
            logger.error(f"Error analyzing element data {data['idx']}: {e}")
            return None
    
    @error_handler
    def _analyze_element_image(self, element: dict, image_data: BytesIO) -> None:
        try:
            with Image.open(image_data) as img:
                width, height = img.size
                if width < 50 or height < 50 or width > 16000 or height > 16000:
                    return

                analysis_result = self.vision_client.analyze_image(image_data)
                if analysis_result:
                    element["text"] = analysis_result.detected_text
                    element["image_caption"] = analysis_result.caption
        except Exception as e:
            logger.error(f"Error analyzing element image: {e}")

    def _analyze_element_specific_data(
        self,
        driver: Optional[WebDriver],
        element: Optional[ClickableElement],
        before_img: np.ndarray,
        after_img: np.ndarray,
        before_styles: dict,
        after_styles: dict,
        device_pixel_ratio: float
    ) -> dict:
        """Analyze element-specific hover changes."""
        if not element or "rect" not in element:
            return {}
            
        try:
            rect = element["rect"]
            x1, y1 = (
                int(rect["left"] * device_pixel_ratio),
                int(rect["top"] * device_pixel_ratio)
            )
            width, height = (
                int(rect["width"] * device_pixel_ratio),
                int(rect["height"] * device_pixel_ratio)
            )

            return {
                "before_color": self.image_processor.get_dominant_color(
                    before_img[y1:y1+height, x1:x1+width]
                ),
                "after_color": self.image_processor.get_dominant_color(
                    after_img[y1:y1+height, x1:x1+width]
                ),
                "size_before": (
                    self.style_manager.parse_css_dimension(before_styles.get("width")),
                    self.style_manager.parse_css_dimension(before_styles.get("height"))
                ),
                "size_after": (
                    self.style_manager.parse_css_dimension(after_styles.get("width")),
                    self.style_manager.parse_css_dimension(after_styles.get("height"))
                ),
                "opacity_before": (
                    self.style_manager.get_element_opacity(driver, element["element"])
                    if driver else None
                ),
                "opacity_after": float(after_styles.get("opacity", 1))
            }
        except Exception as e:
            logger.error(f"Error analyzing element-specific data: {e}")
            return {}
        
    @error_handler
    def analyze_hover_changes(
        self,
        driver: Optional[WebDriver],
        element: Optional[ClickableElement],
        before_img: np.ndarray,
        after_img: np.ndarray,
        before_styles: dict,
        after_styles: dict,
        device_pixel_ratio: float = 1.0
    ) -> Optional[HoverChange]:
        """Analyze hover changes for an element."""
        change_regions = self.image_processor.detect_hover_changes(before_img, after_img)
        if not change_regions:
            return None

        text_analysis = self._analyze_changed_regions(change_regions, after_img)
        element_analysis = self._analyze_element_specific_data(
            driver, element, before_img, after_img, 
            before_styles, after_styles, device_pixel_ratio
        )
        
        return self._create_hover_change(
            change_regions, text_analysis, element_analysis,
            before_styles, after_styles
        )
    
    @error_handler
    def _analyze_hover_data(self, hover_data: dict) -> Optional[dict]:
        try:
            before_img = cv2.imdecode(
                np.frombuffer(hover_data['before_img'].getvalue(), np.uint8),
                cv2.IMREAD_COLOR
            )
            after_img = cv2.imdecode(
                np.frombuffer(hover_data['after_img'].getvalue(), np.uint8),
                cv2.IMREAD_COLOR
            )

            if before_img is None or after_img is None:
                return None

            before_img = cv2.cvtColor(before_img, cv2.COLOR_BGR2RGB)
            after_img = cv2.cvtColor(after_img, cv2.COLOR_BGR2RGB)

            change_regions = self.image_processor.detect_hover_changes(before_img, after_img)
            if not change_regions:
                return None

            # Just analyze style changes and regions without element-specific data
            return HoverChange(
                change_regions=change_regions,
                color_before=None,  # Skip color analysis
                color_after=None,   # Skip color analysis
                size_before=None,   # Skip size analysis
                size_after=None,    # Skip size analysis
                opacity_before=None,
                opacity_after=float(hover_data["after_styles"].get("opacity", 1)),
                cursor_style=hover_data["after_styles"].get("cursor"),
                text_before=hover_data["before_styles"].get("content"),
                text_after=hover_data["after_styles"].get("content")
            )
        
        except Exception as e:
            logger.error(f"Error analyzing hover data: {e}")
            return None
    
    def _analyze_region(
        self,
        region_crop: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int
    ) -> Optional[str]:
        """Analyze a single region for text content."""
        region_pil = Image.fromarray(region_crop)
        temp_path = Path(self.config.screenshot_dir) / f"temp_region_{x1}_{y1}_{x2}_{y2}.png"
        
        try:
            region_pil.save(temp_path)
            region_analysis = self.vision_client.analyze_image(str(temp_path))
            return region_analysis.detected_text if region_analysis else None
        except ValueError as e:
            logger.warning(f"Failed to analyze region: {e}")
            return None
        finally:
            temp_path.unlink(missing_ok=True)

    def _apply_cached_data(self, element: dict) -> dict:
        """Apply cached data to an element if available."""
        element_hash = self._get_element_hash(element)
        if element_hash in self._element_cache:
            element.update(self._element_cache[element_hash])
        return element
    
    @error_handler
    def capture_hover_state(
        self, 
        driver: WebDriver, 
        element: dict, 
        idx: int
    ) -> Optional[dict]:
        try:
            web_element = element["element"]

            # Get initial state
            styles_and_screenshot = js.get_element_hover_state(driver, web_element)
            before_png = driver.get_screenshot_as_png()

            # Simulate hover
            js.hover(driver, web_element)
            time.sleep(0.2)

            # Get post-hover state
            after_styles = js.get_computed_styles(driver, web_element)
            after_png = driver.get_screenshot_as_png()

            # Process images
            before_img = BytesIO()
            after_img = BytesIO()
            Image.open(BytesIO(before_png)).save(before_img, "JPEG", quality=75)
            Image.open(BytesIO(after_png)).save(after_img, "JPEG", quality=75)
            before_img.seek(0)
            after_img.seek(0)

            if self.debug:
                hover_path = Path(self.config.screenshot_dir) / f"hover_{idx}"
                hover_path.mkdir(exist_ok=True)
                Image.open(before_img).save(hover_path / "before.jpg", "JPEG", quality=75)
                Image.open(after_img).save(hover_path / "after.jpg", "JPEG", quality=75)

            return {
                "before_img": before_img,
                "after_img": after_img,
                "before_styles": styles_and_screenshot["styles"],
                "after_styles": after_styles,
                "scroll_positions": [
                    {
                        "left": styles_and_screenshot["scroll"]["x"],
                        "top": styles_and_screenshot["scroll"]["y"],
                    }
                ],
            }
        except Exception as e:
            logger.error(f"Error capturing hover state for element {idx}: {e}")
            return None
    
    @error_handler
    def capture_viewport_data(
        self,
        driver: WebDriver,
        element: dict,
        idx: int,
        detect_hover: bool = False,
    ) -> Optional[dict]:
        """Capture all viewport-dependent data for an element."""
        try:
            logger.info(f"\nCapturing data for element {idx}:")
            logger.info(f"Tag: {element['tag']}")
            logger.info(f"Initial text: {element['text']}")

            # Cache scroll position
            self.scroll_manager.cache_scroll_position(
                driver, element["element"], f"element_{idx}"
            )

            data = {
                "element": element,
                "idx": idx,
                "screenshot": None,
                "hover_data": None,
            }

            # Only skip screenshot for elements with clear text content
            should_capture_screenshot = (
                not element["text"]  # No text
                or element["tag"].lower()
                in {"img", "svg", "canvas"}  # Visual elements
                or "background-image"
                in element.get("style", "")  # Has background image
                or len(element["text"])
                < 3  # Very short text (might be truncated)
            )

            if should_capture_screenshot:
                page_screenshot = driver.get_screenshot_as_png()
                screenshot = self.save_element_screenshot(
                    driver, element, idx, page_screenshot
                )
                if screenshot:
                    data["screenshot"] = screenshot

            # Only capture hover if specifically requested
            if detect_hover:
                hover_data = self.capture_hover_state(driver, element, idx)
                if hover_data:
                    data["hover_data"] = hover_data

            # Restore position after capturing data
            self.scroll_manager.restore_cached_position(
                driver, f"element_{idx}"
            )
            return data

        except Exception as e:
            logger.error(
                f"Error capturing viewport data for element {idx}: {e}"
            )
            return None
    
    def _create_hover_change(
        self,
        change_regions: list[tuple[int, int, int, int]],
        changed_region_texts: list[str],
        element_analysis: dict,
        before_styles: dict,
        after_styles: dict
    ) -> HoverChange:
        """Create a HoverChange instance from analyzed data."""
        text_before = before_styles.get("content")
        text_after = after_styles.get("content")

        if changed_region_texts:
            text_after = (text_after or "") + " " + " ".join(changed_region_texts)
            text_after = text_after.strip()

        before_color = element_analysis.get("before_color")
        after_color = element_analysis.get("after_color")

        return HoverChange(
            change_regions=change_regions,
            color_before=before_color if before_color != after_color else None,
            color_after=after_color if before_color != after_color else None,
            size_before=element_analysis.get("size_before"),
            size_after=element_analysis.get("size_after"),
            opacity_before=element_analysis.get("opacity_before"),
            opacity_after=element_analysis.get("opacity_after"),
            cursor_style=after_styles.get("cursor"),
            text_before=text_before,
            text_after=text_after
        )
    
    @error_handler
    def get_clickable_elements(self, driver: WebDriver) -> list[ClickableElement]:
        """Get all clickable elements with improved efficiency."""
        WebDriverWait(driver, self.config.timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        time.sleep(self.config.parse_delay)

        if self.config.wait_for_network_idle:
            try:
                WebDriverWait(driver, self.config.timeout).until(
                    lambda d: d.execute_script("""
                        return window.performance.getEntriesByType('resource')
                            .filter(r => !r.responseEnd).length === 0
                    """)
                )
            except TimeoutException:
                logger.warning("Network requests didn't complete within timeout!")

        return js.get_clickable_elements(
            driver,
            self.config.viewport_only,
            self.config.min_width,
            self.config.min_height
        )

    @error_handler
    def _get_element_hash(self, element: dict) -> str:
        """Generate a unique hash for an element based on its properties."""
        properties = {
            "tag": element["tag"],
            "text": element["text"],
            "rect": element["rect"],
            "href": element.get("href", ""),
            "src": element.get("src", ""),
            "class": element.get("class", ""),
            "id": element.get("id", "")
        }
        return hashlib.sha256(str(properties).encode()).hexdigest()
    
    def _is_valid_region_size(self, width: int, height: int) -> bool:
        """Check if region dimensions are valid for analysis."""
        return 50 <= width <= 16000 and 50 <= height <= 16000
    
    def _matches_hover_criteria(
        self, 
        element: dict,
        hover_criteria: list[dict]
    ) -> bool:
        """Check if an element matches any of the hover detection criteria."""
        return any(
            all(
                (
                    criteria.get("tag", "").lower() == element["tag"].lower() if "tag" in criteria else True,
                    criteria.get("class", "") in element.get("class", "") if "class" in criteria else True,
                    criteria.get("id", "") == element.get("id", "") if "id" in criteria else True,
                    criteria.get("text", "") in element.get("text", "") if "text" in criteria else True
                )
            )
            for criteria in hover_criteria
        )
    
    @error_handler
    def parallel_analyze_elements(self, element_data: list[dict]) -> list[dict]:
        """Analyze captured element data in parallel."""
        analyzed_elements = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_data = {
                executor.submit(self.analyze_element_data, data): data
                for data in element_data
            }
            
            for future in as_completed(future_to_data):
                data = future_to_data[future]
                try:
                    result = future.result()
                    if result:
                        analyzed_elements.append(result)
                except Exception as e:
                    logger.error(
                        f"Error analyzing element {data['idx']}: {e}"
                    )
                    
        return analyzed_elements
    
    def _process_elements(
        self,
        driver: WebDriver,
        elements: list[dict],
        hover_criteria: Optional[list[dict]]
    ) -> list[dict]:
        """Process all elements with hover detection where specified."""
        processed_elements = []
        element_data = []

        for idx, element in enumerate(elements):
            if not self.should_analyze_element(element):
                processed_elements.append(self._apply_cached_data(element))
                continue

            try:
                should_detect_hover = hover_criteria and self._matches_hover_criteria(
                    element, 
                    hover_criteria
                )
                
                data = self.capture_viewport_data(
                    driver, 
                    element, 
                    idx,
                    detect_hover=should_detect_hover
                )
                if data:
                    element_data.append(data)
            except Exception as e:
                logger.error(f"Error capturing viewport data for element {idx}: {e}")

        analyzed_elements = self.parallel_analyze_elements(element_data)
        processed_elements.extend(analyzed_elements)

        return processed_elements
    
    @error_handler
    def save_element_screenshot(
        self,
        driver: WebDriver,
        element: ClickableElement,
        index: int,
        page_screenshot: Optional[bytes] = None
    ) -> Optional[BytesIO]:
        """Get screenshot of element as BytesIO."""
        web_element = element["element"]

        try:
            rect_info = js.get_element_rect_info(driver, web_element)
            element_rect = rect_info["rect"]

            if (element_rect["width"] <= 0 or 
                element_rect["height"] <= 0 or 
                element_rect["left"] < 0 or 
                element_rect["top"] < 0):
                return None

            js.scroll_element_into_view(driver, web_element, js.get_scroll_needs(driver, web_element))
            time.sleep(0.2)

            screenshot_data = page_screenshot or driver.get_screenshot_as_png()
            screenshot = Image.open(BytesIO(screenshot_data))

            # Process screenshot
            pixel_ratio = rect_info["devicePixelRatio"]
            left = max(0, int(element_rect["left"] * pixel_ratio))
            top = max(0, int(element_rect["top"] * pixel_ratio))
            width = int(element_rect["width"] * pixel_ratio)
            height = int(element_rect["height"] * pixel_ratio)

            img_width, img_height = screenshot.size
            right = min(img_width, left + width)
            bottom = min(img_height, top + height)

            if right <= left or bottom <= top:
                return None

            cropped = screenshot.crop((left, top, right, bottom))

            # Convert to RGB
            if cropped.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', cropped.size, (255, 255, 255))
                background.paste(cropped, mask=cropped.split()[-1])
                cropped = background

            # Save to BytesIO
            img_io = BytesIO()
            cropped.save(img_io, 'JPEG', quality=85)
            img_io.seek(0)

            # Optionally save to file in debug mode
            if self.debug:
                filename = f"{index:03d}_{element['tag'].lower()}_{(element['text'] or '')[:30]}.jpg"
                filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.')).rstrip('.')
                filepath = Path(self.config.screenshot_dir) / filename
                cropped.save(filepath, 'JPEG', quality=85)

            return img_io

        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")
            return None

    def _save_viewport_screenshot(self, driver: WebDriver) -> None:
        """Save the initial viewport screenshot as JPEG for better performance."""
        viewport_path = Path(self.config.screenshot_dir) / "viewport.jpg"
        screenshot = Image.open(BytesIO(driver.get_screenshot_as_png()))
        
        # Convert to RGB if needed (JPEG doesn't support RGBA)
        if screenshot.mode in ("RGBA", "LA"):
            background = Image.new("RGB", screenshot.size, (255, 255, 255))
            background.paste(screenshot, mask=screenshot.split()[-1])
            screenshot = background
            
        screenshot.save(viewport_path, "JPEG", quality=85)

    def setup_screenshot_dir(self) -> None:
        """Setup screenshot directory."""
        if os.path.exists(self.config.screenshot_dir):
            shutil.rmtree(self.config.screenshot_dir)
        os.makedirs(self.config.screenshot_dir, exist_ok=True)
    
    @error_handler
    def should_analyze_element(self, element: dict) -> bool:
        """Determine if an element should be analyzed based on priority rules."""
        # Skip tiny elements
        if element["rect"]["width"] < 20 or element["rect"]["height"] < 20:
            return False
            
        # Skip elements that are likely not important
        low_priority_tags = {"script", "style", "meta", "link", "noscript"}
        if element["tag"].lower() in low_priority_tags:
            return False
            
        # Prioritize interactive elements
        high_priority_tags = {"button", "a", "input", "select", "textarea"}
        if element["tag"].lower() in high_priority_tags:
            return True
            
        # Check if element has been cached
        element_hash = self._get_element_hash(element)
        if element_hash in self._element_cache:
            element.update(self._element_cache[element_hash])
            return False
            
        return True