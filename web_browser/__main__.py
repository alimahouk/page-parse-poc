import json
import time
from io import BytesIO
from pprint import pprint
from typing import Any, Optional

from dotenv import load_dotenv
from PIL import Image
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from web_browser.document_intelligence.client import DocumentClient
from web_browser.document_intelligence.config import ProcessingConfig
from web_browser.document_intelligence.processor import DocumentProcessor
from web_browser.dom.builder import DOMTreeBuilder
from web_browser.dom.models import DOMTree
from web_browser.driver import new_webdriver
from web_browser.vision.client import VisionAnalysisClient
from web_browser.vision.types import (ImageElement, InteractiveElement,
                                      WebpageDescription)
from web_browser.web_analyzer.analyzer import ElementAnalyzer
from web_browser.web_analyzer.config import Config
from web_browser.web_analyzer.element_search import ElementSearchSystem
from web_browser.web_analyzer.elements.merger import ElementMerger
from web_browser.web_analyzer.elements.unified_element import UnifiedElement
from web_browser.web_analyzer.types import HoverChange, PageRegion
from web_browser.web_analyzer.utils import js

load_dotenv()


def build_dom(driver: WebDriver) -> DOMTree:
    builder = DOMTreeBuilder(driver)
    dom_tree = builder.build_tree()
    return dom_tree


def get_element_screenshot(driver: WebDriver, element: UnifiedElement, padding: int = 20) -> Optional[Image.Image]:
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
    screenshot_bytes = driver.get_screenshot_as_png()
    viewport_screenshot = Image.open(BytesIO(screenshot_bytes))

    # Get device pixel ratio for scaling
    dpr = driver.execute_script("return window.devicePixelRatio || 1")
    
    # Scale coordinates by device pixel ratio
    left = max(0, int(element.bounding_box.left * dpr) - padding)
    top = max(0, int(element.bounding_box.top * dpr) - padding)
    right = min(viewport_screenshot.width, int((element.bounding_box.left + element.bounding_box.width) * dpr) + padding)
    bottom = min(viewport_screenshot.height, int((element.bounding_box.top + element.bounding_box.height) * dpr) + padding)
    
    # Ensure coordinates are valid
    if left >= right or top >= bottom:
        return None
        
    # Crop and return
    return viewport_screenshot.crop((left, top, right, bottom))


def get_page_description(driver: WebDriver) -> str:
    screenshot = driver.get_screenshot_as_png()
    viewport_filename = "ui/viewport.jpg"
    image = Image.open(BytesIO(screenshot))
    image.save(viewport_filename)

    vision_client = VisionAnalysisClient.from_env()
    page_description = vision_client.describe_screenshot(viewport_filename)
    serialized = serialize_webpage_description(page_description)
    print("Page Description:")
    pprint(serialized)
    return page_description


def get_unified_elements(
    driver: WebDriver,
    overlap_threshold: float = 0.5
) -> list[UnifiedElement]:
    """
    Get both OCR and clickable elements and merge them into a unified format.
    
    Args:
        driver: WebDriver instance
        overlap_threshold: Threshold for element overlap matching
        
    Returns:
        List of unified elements combining OCR and clickable elements
    """
    # Ensure the screenshot directory exists
    screenshot_dir = "ui"
    viewport_filename = f"{screenshot_dir}/viewport.jpg"

    # Create configuration
    config = Config(
        screenshot_dir=screenshot_dir,
        parse_delay=0,
        viewport_only=True
    )

    # Create analyzer instance
    analyzer = ElementAnalyzer(config)

    # Get clickable elements with screenshots
    clickable_elements = analyzer.analyze_elements(driver)
    print(f"\nFound {len(clickable_elements)} clickable elements.")

    # Initialize document processing components
    client = DocumentClient.from_env()
    processing_config = ProcessingConfig(
        min_confidence=0.8,
        clean_text=True,
        debug_output=True
    )
    processor = DocumentProcessor(client, processing_config)

    # Get OCR elements
    ocr_elements = processor.analyze_read(viewport_filename)
    print(f"Found {len(ocr_elements)} OCR elements.")

    # Get DOM elements
    dom_tree = build_dom(driver)

    # Create element merger and merge elements
    merger = ElementMerger(overlap_threshold=overlap_threshold)
    unified_elements = merger.merge_elements(
        ocr_elements=ocr_elements,
        clickable_elements=clickable_elements,
        dom_tree=dom_tree,
        driver=driver
    )
    print(f"Created {len(unified_elements)} unified elements.")

    return unified_elements


def save_element_screenshot(driver: WebDriver, element: UnifiedElement, filename: Optional[str] = None,
                          padding: int = 70) -> Optional[str]:
        """
        Capture and save a screenshot of a specific UnifiedElement.

        Args:
            element: UnifiedElement to capture
            filename: Optional filename to save the screenshot (default: auto-generated)
            padding: Number of pixels to add around the element (default: 20)

        Returns:
            str or None: Path to the saved screenshot if successful
        """
        element_image = get_element_screenshot(driver, element, padding)
        if not element_image:
            return None

        # Generate filename if not provided
        if not filename:
            element_type = element.element_type or 'unknown'
            content = element.content or 'no_content'
            # Clean content for filename
            content = "".join(c for c in content[:30] if c.isalnum() or c in ("_", "-", ".")).rstrip(".")
            filename = f"element_{element_type}_{content}.png"

        # Ensure filename has .png extension
        if not filename.lower().endswith('.png'):
            filename += '.png'

        # Save to screenshot directory
        output_path = f"ui/{filename}"
        element_image.save(output_path)

        return str(output_path)


def serialize_hover_state(hover_state: HoverChange) -> dict[str, Any]:
    """
    Convert HoverChange object to serializable dict.
    """
    if not hover_state:
        raise ValueError("Expected a HoverChange object")
        
    return {
        "change_regions": hover_state.get("change_regions", []),
        "color_after": hover_state.get("color_after", []),
        "color_before": hover_state.get("color_before", []),
        "cursor_style": hover_state.get("cursor_style", []),
        "opacity_after": hover_state.get("opacity_after", []),
        "opacity_before": hover_state.get("opacity_before", []),
        "size_after": hover_state.get("size_after", []),
        "size_before": hover_state.get("size_before", []),
        "text_after": hover_state.get("text_after", []),
        "text_before": hover_state.get("text_before", []),
    }


def serialize_unified_element(elem: UnifiedElement) -> Optional[dict[str, Any]]:
    """
    Serialize a UnifiedElement instance to a dictionary.
    """
    if not elem:
        return None
    
    # Handle bounding box
    bounding_box_data = None
    if elem.bounding_box:
        bounding_box_data = {
            "left": elem.bounding_box.left,
            "top": elem.bounding_box.top,
            "right": elem.bounding_box.right,
            "bottom": elem.bounding_box.bottom,
            "width": elem.bounding_box.width,
            "height": elem.bounding_box.height
        }
    
    # Safely serialize hover state
    hover_state_data = None
    if elem.hover_state:
        try:
            hover_state_data = serialize_hover_state(elem.hover_state)
        except (ValueError, AttributeError):
            pass
            
    # Serialize link regions, if present
    link_regions_data = None
    if elem.link_regions:
        link_regions_data = []
        for region in elem.link_regions:
            region_bb = {
                "left": region.bounding_box.left,
                "top": region.bounding_box.top,
                "right": region.bounding_box.right,
                "bottom": region.bounding_box.bottom,
                "width": region.bounding_box.width,
                "height": region.bounding_box.height
            }
            link_regions_data.append({
                "bounding_box": region_bb,
                "href": region.href,
                "selector": region.selector,
                "text": region.text,
            })
    
    # Build dictionary with only non-None values
    element_data = {}
    
    if elem.content: element_data["content"] = elem.content
    if elem.element_type: element_data["element_type"] = elem.element_type
    if elem.tag: element_data["tag"] = elem.tag
    if elem.confidence is not None: element_data["confidence"] = elem.confidence
    if bounding_box_data: element_data["bounding_box"] = bounding_box_data
    if elem.screenshots: element_data["screenshots"] = elem.screenshots
    if hover_state_data: element_data["hover_state"] = hover_state_data
    if elem.image_caption: element_data["image_caption"] = elem.image_caption
    if elem.href: element_data["href"] = elem.href
    if elem.src: element_data["src"] = elem.src
    if elem.selector: element_data["selector"] = elem.selector
    if elem.visibility: element_data["visibility"] = elem.visibility
    if elem.dom_text: element_data["dom_text"] = elem.dom_text
    if elem.ocr_text: element_data["ocr_text"] = elem.ocr_text
    if link_regions_data: element_data["link_regions"] = link_regions_data
    
    return element_data


def serialize_webpage_description(description: WebpageDescription) -> dict[str, Any]:
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
            "purpose": image.purpose
        }
    
    # Serialize InteractiveElement objects
    def serialize_interactive(elem: InteractiveElement) -> dict[str, Any]:
        element_data = {
            "type": elem.type,
            "location": elem.location,
            "visuals": elem.visuals,
            "purpose": elem.purpose
        }
        # Add optional fields only if they exist
        if elem.text: element_data["text"] = elem.text
        if elem.state: element_data["state"] = elem.state
        return element_data
    
    # Serialize LayoutSection
    layout_data = {
        "main_content": description.layout.main_content
    }
    # Add optional layout fields if they exist
    if description.layout.header: layout_data["header"] = description.layout.header
    if description.layout.navigation: layout_data["navigation"] = description.layout.navigation
    if description.layout.sidebar: layout_data["sidebar"] = description.layout.sidebar
    
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
            ]
        },
        "visual_hierarchy": {
            "primary_focus": description.visual_hierarchy.primary_focus,
            "secondary_elements": description.visual_hierarchy.secondary_elements,
            "background_elements": description.visual_hierarchy.background_elements
        }
    }


def main():
    driver = new_webdriver(headless=False)
    try:
        driver.get("https://www.amazon.ae/Ricoh-Equipped-with24-2M-Approximately-high-speed/dp/B09FQ7JJ9Y/")
        parse_delay = 30
        time.sleep(parse_delay)
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        print("Beginning now...")
        start_time = time.time()  # Start timing (benchmarking)
        
        js.init(driver)
        
        # Get unified elements
        unified_elements = get_unified_elements(driver)

        # Save unified elements to JSON for analysis
        unified_elements_data = [
            serialized for elem in unified_elements
            if (serialized := serialize_unified_element(elem)) is not None
        ]

        get_page_description(driver)

        end_time = time.time()  # End timing (benchmarking)
        execution_time = end_time - start_time
        # Convert to minutes and seconds
        minutes = int(execution_time // 60)
        seconds = int(execution_time % 60)

        # Save with pretty printing and UTF-8 encoding
        with open("ui/unified_elements.json", "w", encoding="utf-8") as f:
            json.dump(unified_elements_data, f, indent=2, ensure_ascii=False)
        
        if execution_time < 60:
            # Less than a minute, print seconds only
            print(f"\nTotal execution time: {execution_time:.2f} seconds.")
        else:
            # Print in minutes and seconds
            print(f"\nTotal execution time: {minutes} minute(s) {seconds} second(s).")
        
        print("\nPress Enter to close the browser...")
        input()

        query = "buy now"
        print(f"Beginning search test for '{query}'...")
        # Initialize and index page elements
        search_system = ElementSearchSystem()
        search_system.index_elements(unified_elements)
        
        # Search for interactive elements
        search_results = search_system.search(query)
        
        # Example of using results
        for element, score in search_results:
            save_element_screenshot(driver, element)
            print(f"Found {element.tag} element of interest: {element.content} (confidence: {score:.2f})")

        region = PageRegion.TOP_RIGHT
        top_right_elements = search_system.search_by_region(region)
        for element in top_right_elements:
            print(f"Found {element.tag} element of interest in the {region} region: {element.content}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()