"""
Text processing utilities for web analyzer.
"""

from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from web_browser.web_analyzer.elements.unified_element import \
        UnifiedElement


def are_texts_equivalent(text1: str, text2: str, similarity_threshold: float = 0.8) -> bool:
    """
    Check if two texts are effectively equivalent.
    
    Args:
        text1: First text to compare
        text2: Second text to compare
        similarity_threshold: Threshold for considering texts equivalent
        
    Returns:
        True if texts are equivalent
    """
    if not text1 or not text2:
        return False
    
    text1 = normalize_text(text1.lower())
    text2 = normalize_text(text2.lower())
    
    if text1 in text2 or text2 in text1:
        return True
    
    return SequenceMatcher(None, text1, text2).ratio() >= similarity_threshold


def normalize_text(text: str) -> str:
    """
    Normalize text by removing excess whitespace and control characters.
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text string
    """
    if not text:
        return ""
    
    # Remove tabs and normalize line breaks
    text = text.replace("\t", " ")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)


def should_merge_text_fragments(elem1: "UnifiedElement", elem2: "UnifiedElement", 
                              max_vertical_gap: float = 25.0) -> bool:
    """
    Determine if two text elements should be merged.
    
    Args:
        elem1: First element to check
        elem2: Second element to check
        max_vertical_gap: Maximum allowed vertical gap between elements
        
    Returns:
        True if elements should be merged
    """
    if not (elem1.bounding_box and elem2.bounding_box):
        return False
    
    if (elem1.dom_text and elem2.dom_text and elem1.dom_text == elem2.dom_text) or \
       (elem1.selector and elem2.selector and elem1.selector == elem2.selector):
        return True
    
    bb1, bb2 = elem1.bounding_box, elem2.bounding_box
    vertical_gap = min(abs(bb1.bottom - bb2.top), abs(bb2.bottom - bb1.top))
    
    return (vertical_gap <= max_vertical_gap and 
            abs(bb1.left - bb2.left) < 50 and 
            elem1.tag == elem2.tag and 
            elem1.visibility == elem2.visibility)