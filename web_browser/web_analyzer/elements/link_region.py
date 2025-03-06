"""
Module for handling link regions within elements.
"""

from dataclasses import dataclass
from typing import Optional

from web_browser.web_analyzer.elements.bounding_box import BoundingBox


@dataclass
class LinkRegion:
    """
    Represents a clickable link region within text content.
    
    Attributes:
        bounding_box: Geometric bounds of the link region
        href: URL the link points to
        selector: CSS selector for the link element
        text: Text content of the link
    """
    bounding_box: BoundingBox
    href: str
    selector: Optional[str]
    text: str


def deduplicate_link_regions(regions: list[LinkRegion]) -> list[LinkRegion]:
    """
    Remove duplicate link regions based on text, href, and selector.
    
    Args:
        regions: List of LinkRegion instances to deduplicate
        
    Returns:
        List of unique LinkRegion instances
    """
    seen = set()
    unique_regions = []
    
    for region in regions:
        key = (region.text, region.href, region.selector)
        if key not in seen:
            seen.add(key)
            unique_regions.append(region)
            
    return unique_regions


def extract_link_regions(text: str, dom_elements: list["UnifiedElement"], 
                        text_box: BoundingBox) -> list[LinkRegion]:
    """
    Extract link regions from text content.
    
    Args:
        text: Text content to analyze
        dom_elements: List of DOM elements to match against
        text_box: Bounding box of the text container
        
    Returns:
        List of LinkRegion instances found in the text
    """
    anchor_elements = [
        elem for elem in dom_elements 
        if elem.tag.lower() == "a" and 
        elem.href and 
        elem.dom_text and 
        elem.bounding_box and
        (elem.bounding_box.calculate_overlap(text_box) >= 0.5 or
         (abs(elem.bounding_box.left - text_box.left) < 10 and
          abs(elem.bounding_box.right - text_box.right) < 10 and
          abs(elem.bounding_box.top - text_box.bottom) < 20))
    ]
    
    anchor_elements.sort(key=lambda x: len(x.dom_text or ""), reverse=True)
    link_regions = []
    
    for anchor in anchor_elements:
        anchor_text = anchor.dom_text.strip()
        if not anchor_text or not text:
            continue
        
        start_idx = text.lower().find(anchor_text.lower())
        if start_idx >= 0:
            matched_text = text[start_idx:start_idx + len(anchor_text)]
            
            if (matched_text.strip() == text.strip() and
                    anchor.bounding_box.is_almost_equal(text_box)):
                continue
            
            link_regions.append(LinkRegion(
                text=matched_text,
                href=anchor.href,
                selector=anchor.selector,
                bounding_box=anchor.bounding_box
            ))
    
    return link_regions