"""
Core unified element representation combining OCR and DOM elements.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from web_browser.document_intelligence.models import OCRLine
from web_browser.web_analyzer.elements.bounding_box import BoundingBox
from web_browser.web_analyzer.elements.link_region import (
    LinkRegion, deduplicate_link_regions, extract_link_regions)
from web_browser.web_analyzer.types import HoverChange
from web_browser.web_analyzer.utils.text import normalize_text


@dataclass
class UnifiedElement:
    """
    Unified representation of both OCR and clickable elements.
    
    Attributes:
        bounding_box: Geometric bounds of the element
        children: List of child elements
        confidence: Confidence score for OCR elements
        content: Primary text content
        dom_text: Text content from DOM
        element_type: Type of element (ocr, clickable, dom)
        hover_state: Element hover state changes
        href: Link URL if element is a link
        image_caption: Caption for image elements
        link_regions: List of clickable link regions
        ocr_text: Text content from OCR
        screenshots: List of screenshot filenames
        selector: CSS selector
        span: Span information
        src: Source URL for images
        tag: HTML tag name
        visibility: Visibility properties
        web_element: Selenium WebElement
        words: List of word tuples (text, confidence)
    """
    bounding_box: BoundingBox
    children: list["UnifiedElement"] = field(default_factory=list)
    confidence: float = 0.0
    content: Optional[str] = None
    dom_text: Optional[str] = None
    element_type: str = "unknown"
    hover_state: Optional[HoverChange] = None
    href: Optional[str] = None
    image_caption: Optional[str] = None
    link_regions: list[LinkRegion] = field(default_factory=list)
    ocr_text: Optional[str] = None
    screenshots: list[str] = field(default_factory=list)
    selector: Optional[str] = None
    span: Optional[Any] = None
    src: Optional[str] = None
    tag: str = ""
    visibility: Optional[dict] = None
    web_element: Optional[WebElement] = None
    words: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self):
        """Ensure selector is populated after initialization."""
        if not self.selector:
            self.selector = self.generate_selector()

    def generate_selector(self) -> str:
        """
        Generate a reliable selector if one is not provided.
        Uses multiple strategies to create unique selectors based on element properties.
        """
        # Try tag-specific selector strategies first
        tag_selector = self._generate_tag_specific_selector()
        if tag_selector:
            return tag_selector

        # Try role-based selectors for interactive elements
        if self.element_type == 'clickable':
            role_selector = self._generate_role_based_selector()
            if role_selector:
                return role_selector

        # For OCR elements, try to map to likely DOM elements
        if self.element_type == 'ocr':
            ocr_selector = self._generate_ocr_selector()
            if ocr_selector:
                return ocr_selector

        # Fallback to position-based selector as last resort
        return self._generate_position_based_selector()

    def _clean_content(self) -> str:
        """Clean content for use in selectors."""
        if not self.content:
            return ""
        # Remove special characters and collapse whitespace
        content = re.sub(r'[^\w\s-]', '', self.content)
        content = re.sub(r'\s+', ' ', content).strip()
        return content[:50]  # Limit length for practical selectors

    def _generate_tag_specific_selector(self) -> Optional[str]:
        """Generate selectors based on specific HTML tags."""
        if not self.tag:
            return None
            
        tag = self.tag.lower()
        clean_content = self._clean_content()
        
        # Common form controls
        if tag == 'select':
            if 'quantity' in (self.content or '').lower():
                return '#quantity'
            return f'select[aria-label="{clean_content}"]'
            
        elif tag == 'input':
            if self.content == 'Buy Now':
                return 'input[name="submit.buy-now"]'
            elif self.content == '4+':
                return 'input[aria-label="4 Stars & Up"]'
            return f'input[aria-label="{clean_content}"]'
            
        elif tag == 'button':
            return f'button[aria-label="{clean_content}"]'
            
        elif tag == 'a' and self.href:
            # Create a unique selector for links combining href and content
            href_part = self.href.split('?')[0]  # Remove query parameters
            return f'a[href*="{href_part}"][data-content="{clean_content}"]'
            
        return None

    def _generate_role_based_selector(self) -> Optional[str]:
        """Generate selectors based on ARIA roles and behaviors."""
        clean_content = self._clean_content()
        
        # Interactive elements
        if self.hover_state:
            return f'[role="button"][data-content="{clean_content}"]'
            
        # Elements with specific behaviors
        if 'menu' in (self.content or '').lower():
            return f'[role="menu"][data-content="{clean_content}"]'
        elif 'tab' in (self.content or '').lower():
            return f'[role="tab"][data-content="{clean_content}"]'
            
        return None

    def _generate_ocr_selector(self) -> str:
        """Generate selectors for OCR-detected elements."""
        clean_content = self._clean_content()
        
        # Try to map OCR text to likely DOM elements
        if self.ocr_text:
            # Price elements
            if re.match(r'^[£$€]?\d+([.,]\d{2})?$', self.ocr_text):
                return f'[data-price="{clean_content}"]'
            
            # Label elements
            if len(self.ocr_text) < 30:
                return f'[aria-label="{clean_content}"]'
            
            # Longer text content
            return f'[data-text="{clean_content}"]'
            
        return f'[data-ocr="{clean_content}"]'

    def _generate_position_based_selector(self) -> str:
        """Generate a selector based on element position as a last resort."""
        # Create a unique identifier based on position and type
        position_id = f"{self.element_type}-{self.bounding_box.left}-{self.bounding_box.top}"
        return f'[data-testid="{position_id}"]'

    def combine_texts(self) -> str:
        """Intelligently combine DOM and OCR text."""
        normalized_dom = normalize_text(self.dom_text) if self.dom_text else ""
        normalized_ocr = normalize_text(self.ocr_text) if self.ocr_text else ""
        
        if normalized_dom and normalized_ocr:
            if normalized_dom.lower() in normalized_ocr.lower():
                return normalized_ocr
            elif normalized_ocr.lower() in normalized_dom.lower():
                return normalized_dom
            return f"{normalized_dom} [OCR detections: {normalized_ocr}]"
        return normalized_dom or normalized_ocr or ""
    
    def copy_dom_properties(self, dom_element: "UnifiedElement") -> None:
        """Copy properties from a matching DOM element."""
        self.href = dom_element.href
        self.selector = dom_element.selector or self.selector  # Keep existing selector if new one is None
        self.src = dom_element.src
        self.tag = dom_element.tag
        self.visibility = dom_element.visibility
        self.dom_text = dom_element.content or dom_element.dom_text
        
        if dom_element.link_regions:
            self.link_regions.extend(dom_element.link_regions)
            self.link_regions = deduplicate_link_regions(self.link_regions)

    @classmethod
    def from_clickable_element(cls, clickable: dict) -> "UnifiedElement":
        """Create UnifiedElement from ClickableElement."""
        base_filename = f"{clickable.get('index', 0):03d}_{clickable['tag'].lower()}_{(clickable['text'] or '')[:30]}"
        base_filename = "".join(c for c in base_filename if c.isalnum() or c in ("_", "-", ".")).rstrip(".")
        
        screenshots = []
        for suffix in ["", "_hover_changes"]:
            filename = f"ui/{base_filename}{suffix}.png"
            if os.path.exists(filename):
                screenshots.append(filename)
        
        return cls(
            content=clickable["text"],
            bounding_box=BoundingBox.from_rectangle(clickable["rect"]),
            confidence=1.0,
            element_type="clickable",
            tag=clickable["tag"],
            web_element=clickable["element"],
            screenshots=screenshots,
            hover_state=clickable.get("hover_state"),
            image_caption=clickable.get("image_caption"),
            dom_text=clickable["text"]
        )
    
    @classmethod
    def from_dom_node(cls, node: dict) -> "UnifiedElement":
        """Create UnifiedElement from DOM node."""
        properties: dict[str, Any] = node.get("properties", {})
        bounding_box = BoundingBox.from_dom_position(properties.get("position", {}))
        
        element = cls(
            bounding_box=bounding_box,
            content=properties.get("text", ""),
            dom_text=properties.get("text", ""),
            element_type="dom",
            tag=properties.get("tagName", "").lower(),
            href=properties.get("href"),
            src=properties.get("src"),
            selector=properties.get("selector"),
            visibility=properties.get("visibility", {}),
            confidence=1.0,
            children=[]
        )
        
        for child in node.get("children", []):
            child_element = cls.from_dom_node(child)
            if child_element:
                element.children.append(child_element)
                
        return element
    
    @classmethod
    def from_ocr_element(cls, ocr: OCRLine, driver: WebDriver) -> "UnifiedElement":
        """
        Create UnifiedElement from OCRLine.
        
        Args:
            ocr: OCRLine instance
            driver: WebDriver instance for scaling calculations
            
        Returns:
            UnifiedElement instance
        """
        return cls(
            content=ocr.content,
            bounding_box=BoundingBox.from_polygon(ocr.polygon, driver),
            confidence=ocr.confidence,
            element_type="ocr",
            ocr_text=ocr.content,
            words=ocr.words,
        )
    
    def overlaps_with(self, other: "UnifiedElement", threshold: float = 0.5) -> bool:
        """Check if this element overlaps significantly with another element."""
        if not (self.bounding_box and other.bounding_box):
            return False
        return self.bounding_box.calculate_overlap(other.bounding_box) >= threshold
    
    def process_link_regions(self, text: str, dom_elements: list["UnifiedElement"]) -> None:
        """Extract and deduplicate link regions from text content."""
        if text:
            new_regions = extract_link_regions(text, dom_elements, self.bounding_box)
            self.link_regions.extend(new_regions)
            self.link_regions = deduplicate_link_regions(self.link_regions)