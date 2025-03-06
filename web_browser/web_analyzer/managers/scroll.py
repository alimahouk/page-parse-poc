"""Manager for optimized scroll operations."""

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from web_browser.web_analyzer.utils import js


@dataclass
class ScrollGroup:
    """Represents a group of elements at similar vertical positions."""
    elements: list[dict]
    y_position: int
    processed: bool = False

class ScrollManager:
    """Manages scroll positions and operations with optimized strategies."""
    
    def __init__(self, group_size: int = 500):
        self._group_size = group_size
        self._scroll_positions_cache: dict[str, list[dict[str, Any]]] = {}
        
    def group_elements(self, driver: WebDriver, elements: list[dict]) -> dict[int, ScrollGroup]:
        """Group elements by their vertical position for optimized scrolling."""
        positions = js.get_element_positions(driver, elements)
        groups: dict[int, ScrollGroup] = {}
        
        for position in positions:
            group_index = position['y_position'] // self._group_size
            
            if group_index not in groups:
                groups[group_index] = ScrollGroup(
                    y_position=group_index * self._group_size,
                    elements=[]
                )
            
            groups[group_index].elements.append(position['element'])
            
        return groups

    def calculate_scroll_sequence(self, driver: WebDriver, groups: dict[int, ScrollGroup]) -> list[tuple[int, int]]:
        """Calculate optimal scroll sequence."""
        scroll_sequence = []
        current_pos = 0

        for group_index in sorted(groups.keys()):
            target_y = groups[group_index].y_position
            scroll_amount = target_y - current_pos

            # Only add to sequence if significant scroll needed
            viewport = js.get_viewport_size(driver)
            if abs(scroll_amount) > viewport['height'] / 3:
                scroll_sequence.append((0, scroll_amount))
                current_pos = target_y

        return scroll_sequence

    def cache_scroll_position(self, driver: WebDriver, element: WebElement, key: str) -> None:
        """Cache scroll positions for an element."""
        positions = js.get_scroll_elements(driver, element)
        self._scroll_positions_cache[key] = positions

    def restore_cached_position(self, driver: WebDriver, key: str) -> bool:
        """Restore scroll positions from cache."""
        if key not in self._scroll_positions_cache:
            return False
            
        positions = self._scroll_positions_cache[key]
        js.disable_smooth_scrolling(driver)
        js.restore_scroll_positions(driver, positions)
        time.sleep(0.5)
        return True

    def process_elements_in_viewport(
        self, 
        driver: WebDriver,
        elements: list[dict],
        viewport_callback: Optional[Callable[[list[dict]], None]] = None
    ) -> None:
        """Process all elements using optimal scrolling strategy."""
        # Group elements
        groups = self.group_elements(driver, elements)
        scroll_sequence = self.calculate_scroll_sequence(driver, groups)
        
        # Execute scroll sequence
        for x_scroll, y_scroll in scroll_sequence:
            # Scroll to position
            js.scroll_by(driver, x_scroll, y_scroll)
            time.sleep(0.5)
            
            # Get elements currently in viewport
            visible_elements = js.get_viewport_elements(driver, elements)
            
            # Process visible elements if callback provided
            if viewport_callback and visible_elements:
                viewport_callback(visible_elements)

    # Original methods maintained for compatibility
    @staticmethod
    def get_positions(driver: WebDriver, element: WebElement) -> list[dict[str, Any]]:
        """Get original scroll positions for all scrollable parent elements."""
        return js.get_scroll_elements(driver, element)

    @staticmethod
    def restore_positions(driver: WebDriver, positions: list[dict[str, Any]]) -> None:
        """Restore scroll positions with smooth scrolling disabled."""
        if not positions:
            return

        js.disable_smooth_scrolling(driver)
        js.restore_scroll_positions(driver, positions)
        time.sleep(0.3)

    @staticmethod
    def scroll_into_view(driver: WebDriver, element: WebElement) -> None:
        """Scroll an element into view."""
        scroll_info = js.get_scroll_needs(driver, element)
        js.scroll_element_into_view(driver, element, scroll_info)
        time.sleep(0.3)