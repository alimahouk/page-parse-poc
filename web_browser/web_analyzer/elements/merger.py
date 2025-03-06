"""
Element merging functionality for combining OCR and DOM elements.
"""

from collections import defaultdict
from typing import Any, Optional

from selenium.webdriver.chrome.webdriver import WebDriver

from web_browser.web_analyzer.elements.link_region import LinkRegion
from web_browser.web_analyzer.elements.unified_element import UnifiedElement
from web_browser.web_analyzer.utils.text import should_merge_text_fragments


class ElementMerger:
    """
    Handles merging of OCR and DOM elements into unified representations.
    """
    
    def __init__(self, overlap_threshold: float = 0.5):
        """
        Initialize the ElementMerger.
        
        Args:
            overlap_threshold: Minimum overlap ratio to consider elements matching
        """
        self.overlap_threshold = overlap_threshold
    
    def _create_paragraph_links_mapping(
        self, clickable_elements: list[Any]
    ) -> dict[str, list[UnifiedElement]]:
        """Create mapping of paragraph selectors to their link elements."""
        paragraph_links: dict[str, list[UnifiedElement]] = defaultdict(list)
        
        for clickable in clickable_elements:
            if not clickable:
                continue
            
            element = UnifiedElement.from_clickable_element(clickable)
            if not element or not element.selector:
                continue
                
            if element.tag.lower() == "a" and "p:nth-child" in element.selector:
                parts = element.selector.split(" > ")
                paragraph_selector = " > ".join(parts[:-1])
                paragraph_links[paragraph_selector].append(element)
                
        return paragraph_links
    
    def _extract_dom_elements(
        self, dom_tree: dict[str, Any], paragraph_links: dict[str, list[UnifiedElement]]
    ) -> list[UnifiedElement]:
        """Extract DOM elements with their properties."""
        dom_elements: list[UnifiedElement] = []
        
        def collect_dom_elements(node: dict[str, Any]) -> None:
            if not node or not isinstance(node, dict):
                return
                
            props = node.get("properties")
            if props and props.get("position"):
                element = UnifiedElement.from_dom_node(node)
                if element and element.bounding_box:
                    if (element.tag.lower() == "p" and 
                        element.selector in paragraph_links):
                        element.link_regions = [
                            LinkRegion(
                                text=link.dom_text or link.content or "",
                                href=link.href or "",
                                selector=link.selector,
                                bounding_box=link.bounding_box
                            ) for link in paragraph_links[element.selector]
                            if link.bounding_box
                        ]
                    dom_elements.append(element)
                    
            for child in node.get("children", []):
                collect_dom_elements(child)
        
        try:
            for child in dom_tree.get("children", []):
                collect_dom_elements(child)
        except Exception as e:
            print(f"Error collecting DOM elements: {e}")
            
        return dom_elements
    
    def _find_matching_dom_element(
        self, element: UnifiedElement, dom_elements: list[UnifiedElement]
    ) -> Optional[UnifiedElement]:
        """Find best matching DOM element."""
        if not element or not element.bounding_box:
            return None
            
        best_match = None
        best_overlap = self.overlap_threshold
        
        for dom_elem in dom_elements:
            if not dom_elem or not dom_elem.bounding_box:
                continue
                
            overlap = element.bounding_box.calculate_overlap(dom_elem.bounding_box)
            if overlap <= best_overlap:
                continue

            if element.element_type == "ocr":
                dom_text = (dom_elem.content or dom_elem.dom_text or "").strip().lower()
                ocr_text = (element.content or "").strip().lower()
                
                if dom_text and (dom_text in ocr_text or ocr_text in dom_text):
                    best_overlap = overlap
                    best_match = dom_elem
            elif element.tag.lower() == dom_elem.tag.lower():
                best_overlap = overlap
                best_match = dom_elem
                    
        return best_match
    
    def merge_elements(
        self,
        ocr_elements: list[Any],
        clickable_elements: list[Any],
        dom_tree: dict[str, Any],
        driver: WebDriver
    ) -> list[UnifiedElement]:
        """
        Merge clickable and OCR elements with their matching DOM elements.
        
        Args:
            ocr_elements: List of OCR elements
            clickable_elements: List of clickable elements
            dom_tree: DOM tree structure
            driver: WebDriver instance
            
        Returns:
            List of merged UnifiedElement instances
        """
        unified_elements: list[UnifiedElement] = []
        dom_elements: list[UnifiedElement] = []
        
        if not dom_tree:
            return []

        # Create paragraph_links mapping
        paragraph_links = self._create_paragraph_links_mapping(clickable_elements)
        
        # Extract DOM elements
        dom_elements = self._extract_dom_elements(dom_tree, paragraph_links)
        
        # Process clickable elements
        unified_elements.extend(
            self._process_clickable_elements(clickable_elements, dom_elements)
        )
        
        # Process OCR elements
        unified_elements.extend(
            self._process_ocr_elements(ocr_elements, dom_elements, driver)
        )
        
        # Final merging of text fragments
        return self._merge_text_fragments(unified_elements)
    
    def _merge_text_fragments(self, elements: list[UnifiedElement]) -> list[UnifiedElement]:
        """Merge text fragments by tag."""
        elements_by_tag = defaultdict(list)
        for elem in elements:
            elements_by_tag[elem.tag or ""].append(elem)
        
        final_elements = []
        
        for elements in elements_by_tag.values():
            elements.sort(key=lambda e: e.bounding_box.top if e.bounding_box else float('inf'))
            
            i = 0
            while i < len(elements):
                current = elements[i]
                merged = current
                
                j = i + 1
                while j < len(elements):
                    next_elem = elements[j]
                    if should_merge_text_fragments(merged, next_elem):
                        # Create new merged element
                        content = []
                        if merged.content:
                            content.append(merged.content)
                        if next_elem.content:
                            content.append(next_elem.content)
                        
                        merged = UnifiedElement(
                            content=" ".join(content),
                            bounding_box=merged.bounding_box.merge_with(next_elem.bounding_box),
                            element_type=merged.element_type,
                            tag=merged.tag,
                            confidence=max(merged.confidence or 0.0, next_elem.confidence or 0.0),
                            dom_text=merged.dom_text or next_elem.dom_text,
                            ocr_text=" ".join(filter(None, [merged.ocr_text, next_elem.ocr_text])),
                            selector=merged.selector or next_elem.selector,
                            visibility=merged.visibility or next_elem.visibility
                        )
                        j += 1
                    else:
                        break
                        
                final_elements.append(merged)
                i = j if j > i + 1 else i + 1
        
        return final_elements
    
    def _process_clickable_elements(
        self, clickable_elements: list[Any], dom_elements: list[UnifiedElement]
    ) -> list[UnifiedElement]:
        """Process and merge clickable elements."""
        unified_elements = []
        
        for clickable in clickable_elements:
            if not clickable:
                continue
                
            element = UnifiedElement.from_clickable_element(clickable)
            if not element:
                continue

            element.process_link_regions(element.content, dom_elements)
            
            dom_match = self._find_matching_dom_element(element, dom_elements)
            if dom_match:
                element.copy_dom_properties(dom_match)
            
            unified_elements.append(element)
            
        return unified_elements
    
    def _process_ocr_elements(
        self, ocr_elements: list[Any], dom_elements: list[UnifiedElement], driver: WebDriver
    ) -> list[UnifiedElement]:
        """Process and merge OCR elements."""
        unified_elements = []
        processed_indices = set()
        
        for i, ocr in enumerate(ocr_elements):
            if i in processed_indices or not ocr:
                continue
                
            element = UnifiedElement.from_ocr_element(ocr, driver)
            if not element:
                continue

            # Look for vertically adjacent elements to merge
            merged_content = [element.content] if element.content else []
            merged_words = element.words.copy() if element.words else []
            
            # Check subsequent elements for vertical merging
            for j, next_ocr in enumerate(ocr_elements[i + 1:], start=i + 1):
                if j in processed_indices:
                    continue
                    
                next_element = UnifiedElement.from_ocr_element(next_ocr, driver)
                if not next_element:
                    continue
                    
                if should_merge_text_fragments(element, next_element):
                    if next_element.content:
                        merged_content.append(next_element.content)
                    if next_element.words:
                        merged_words.extend(next_element.words)
                    processed_indices.add(j)
                    
                    if element.bounding_box and next_element.bounding_box:
                        element.bounding_box = element.bounding_box.merge_with(
                            next_element.bounding_box
                        )
                else:
                    break
                    
            if len(merged_content) > 1:
                element.content = " ".join(merged_content)
                element.words = merged_words
            
            element.process_link_regions(element.content, dom_elements)
            
            dom_match = self._find_matching_dom_element(element, dom_elements)
            if dom_match:
                element.copy_dom_properties(dom_match)
            
            unified_elements.append(element)
            processed_indices.add(i)
            
        return unified_elements