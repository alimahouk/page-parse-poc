"""
JavaScript utility functions for web element analysis.
"""

from typing import Any

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement


def disable_smooth_scrolling(driver: WebDriver) -> None:
    """Disable smooth scrolling behavior."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    driver.execute_script("""
        const style = document.createElement('style');
        style.textContent = '* { scroll-behavior: auto !important; }';
        document.head.appendChild(style);
    """)

    
def get_clickable_elements(
    driver: WebDriver,
    viewport_only: bool,
    min_width: int,
    min_height: int
) -> list[dict]:
    """Get all clickable elements matching criteria."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    return driver.execute_script("""
        const CLICKABLE_TAGS = new Set([
            'BUTTON', 'A', 'SELECT', 'INPUT', 'TEXTAREA', 'LABEL',
            'SUMMARY', 'DIALOG', 'VIDEO', 'AUDIO', 'DETAILS', 'MENU'
        ]);
        
        const CLICKABLE_CURSORS = new Set([
            'help', 'pointer', 'zoom-in', 'zoom-out', 'grab',
            'grabbing', 'cell', 'crosshair', 'move'
        ]);
        
        return Array.from(document.querySelectorAll(
            'button, a, select, input, textarea, label, summary, dialog, ' +
            'video, audio, details, menu, [onclick], [role], [tabindex]'
        )).map(element => {
            const rect = element.getBoundingClientRect();
            const style = window.getComputedStyle(element);
            
            const isInViewport = !(
                rect.bottom < 0 || rect.top > window.innerHeight ||
                rect.right < 0 || rect.left > window.innerWidth
            );
            
            const isVisible = (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                style.opacity !== '0'
            );
            
            const textContent = element.textContent.trim() ||
                element.getAttribute('aria-label') ||
                element.getAttribute('title') ||
                element.getAttribute('placeholder') ||
                element.getAttribute('name') ||
                element.getAttribute('value') ||
                element.getAttribute('alt') ||
                '';
            
            const dimensions = {
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: rect.height
            };
            
            const include = isVisible && 
                (!arguments[0] || isInViewport) && (
                    CLICKABLE_TAGS.has(element.tagName) ||
                    element.onclick != null ||
                    CLICKABLE_CURSORS.has(style.cursor)
                );
            
            return {
                element: element,
                tag: element.tagName,
                include: include,
                rect: dimensions,
                text: textContent
            };
        }).filter(item => (
            item.include &&
            item.rect.width >= arguments[1] &&
            item.rect.height >= arguments[2]
        ));
    """, viewport_only, min_width, min_height)


def get_computed_styles(driver: WebDriver, element: WebElement) -> dict[str, str]:
    """Get computed styles for an element."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    return driver.execute_script("""
        const styles = window.getComputedStyle(arguments[0]);
        const relevantStyles = [
            'width', 'height', 'color', 'backgroundColor', 'borderColor',
            'borderWidth', 'opacity', 'cursor', 'content', 'transform',
            'boxShadow', 'textDecoration'
        ];
        return Object.fromEntries(
            relevantStyles.map(style => [style, styles[style]])
        );
    """, element)


def get_element_hover_state(driver: WebDriver, element: WebElement) -> dict:
    """Get element's computed styles and scroll position before hover."""
    if not driver:
        raise ValueError("Driver is not initialized")
        
    return driver.execute_script(
        """
        const element = arguments[0];
        const styles = window.getComputedStyle(element);
        const before = {
            width: styles.width,
            height: styles.height,
            color: styles.color,
            backgroundColor: styles.backgroundColor,
            opacity: styles.opacity,
            cursor: styles.cursor,
            content: styles.content
        };
        return {
            styles: before,
            scroll: {
                x: window.scrollX,
                y: window.scrollY
            }
        };
        """,
        element,
    )


def get_element_positions(driver: WebDriver, elements: list[dict]) -> list[dict]:
    """Get vertical positions of all elements for grouping."""
    if not driver:
        raise ValueError("Driver is not initialized")
        
    return driver.execute_script(
        """
        return arguments[0].map(element => {
            const rect = element.element.getBoundingClientRect();
            return {
                element: element,
                y_position: rect.top + window.scrollY
            };
        });
        """,
        elements
    )


def get_element_rect_info(driver: WebDriver, element: WebElement) -> dict[str, Any]:
    """Get element's rectangle info with device pixel ratio."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    return driver.execute_script("""
        const rect = arguments[0].getBoundingClientRect();
        return {
            rect: {
                top: rect.top + window.scrollY,
                left: rect.left + window.scrollX,
                width: rect.width,
                height: rect.height
            },
            devicePixelRatio: window.devicePixelRatio || 1
        };
    """, element)


def get_mouse_position(driver: WebDriver) -> tuple[int, int]:
    """Get the current mouse position relative to the viewport."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    mouse_pos = driver.execute_script("""
        if (typeof window.mousePosition === 'undefined') {
            window.mousePosition = {x: 0, y: 0};
            document.addEventListener('mousemove', (e) => {
                window.mousePosition = {
                    x: e.clientX,
                    y: e.clientY
                };
            });
        }
        return window.mousePosition;
    """)
    return (mouse_pos["x"], mouse_pos["y"])


def get_scroll_elements(driver: WebDriver, element: WebElement) -> list[dict]:
    """Get all scrollable parent elements and their current scroll positions."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    return driver.execute_script("""
        function getScrollElements(element) {
            let elements = [];
            let parent = element.parentElement;
            
            while (parent) {
                if (parent.scrollWidth > parent.clientWidth || 
                    parent.scrollHeight > parent.clientHeight) {
                    elements.push({
                        element: parent,
                        left: parent.scrollLeft,
                        top: parent.scrollTop
                    });
                }
                parent = parent.parentElement;
            }
            return elements;
        }
        return getScrollElements(arguments[0]);
    """, element)


def get_scroll_needs(driver: WebDriver, element: WebElement) -> dict[str, Any]:
    """Analyze element's scroll requirements and find scrollable parents."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    return driver.execute_script("""
        function getScrollNeeds(element) {
            const rect = element.getBoundingClientRect();
            const viewWidth = Math.max(document.documentElement.clientWidth, window.innerWidth);
            const viewHeight = Math.max(document.documentElement.clientHeight, window.innerHeight);
            
            const needsHorizontal = rect.left < 0 || rect.right > viewWidth;
            const needsVertical = rect.top < 0 || rect.bottom > viewHeight;
            
            let horizontalParent = null;
            let verticalParent = null;
            let parent = element.parentElement;
            
            while (parent) {
                const style = window.getComputedStyle(parent);
                const hasHorizontalScroll = parent.scrollWidth > parent.clientWidth;
                const hasVerticalScroll = parent.scrollHeight > parent.clientHeight;
                const canScrollHorizontal = ['auto', 'scroll'].includes(style.overflowX);
                const canScrollVertical = ['auto', 'scroll'].includes(style.overflowY);
                
                if (!horizontalParent && hasHorizontalScroll && canScrollHorizontal) {
                    horizontalParent = parent;
                }
                if (!verticalParent && hasVerticalScroll && canScrollVertical) {
                    verticalParent = parent;
                }
                if (horizontalParent && verticalParent) break;
                parent = parent.parentElement;
            }
            
            return {
                needs: {
                    horizontal: needsHorizontal,
                    vertical: needsVertical
                },
                parents: {
                    horizontal: horizontalParent,
                    vertical: verticalParent
                },
                elementRect: rect
            };
        }
        return getScrollNeeds(arguments[0]);
    """, element)


def get_viewport_elements(driver: WebDriver, elements: list[dict]) -> list[dict]:
    """Get elements currently visible in the viewport."""
    if not driver:
        raise ValueError("Driver is not initialized")
        
    return driver.execute_script(
        """
        function isInViewport(rect) {
            return (
                rect.top >= 0 &&
                rect.left >= 0 &&
                rect.bottom <= window.innerHeight &&
                rect.right <= window.innerWidth
            );
        }
        
        return arguments[0].filter(element => {
            const rect = element.element.getBoundingClientRect();
            return isInViewport(rect);
        });
        """,
        elements
    )


def get_viewport_size(driver: WebDriver) -> dict[str, int]:
    """Get the current viewport dimensions."""
    if not driver:
        raise ValueError("Driver is not initialized")
        
    return driver.execute_script(
        """
        return {
            width: window.innerWidth,
            height: window.innerHeight
        };
        """
    )


def hover(driver: WebDriver, element: WebElement) -> None:
    """Trigger a hover event on the element."""
    if not driver:
        raise ValueError("Driver is not initialized")
        
    driver.execute_script(
        """
        const element = arguments[0];
        const rect = element.getBoundingClientRect();
        const event = new MouseEvent('mouseover', {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: rect.left + rect.width/2,
            clientY: rect.top + rect.height/2
        });
        element.dispatchEvent(event);
        """,
        element,
    )


def init(driver: WebDriver) -> None:
    """Initialize JavaScript utilities."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    # Set up a tracker for the mouse position
    driver.execute_script("""
        window.mousePosition = {x: 0, y: 0};
        document.addEventListener('mousemove', (e) => {
            window.mousePosition = {
                x: e.clientX,
                y: e.clientY
            };
        });
    """)

def restore_scroll_positions(driver: WebDriver, positions: list[dict]) -> None:
    """Restore scroll positions for multiple elements."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    driver.execute_script("""
        const positions = arguments[0];
        positions.forEach(pos => {
            pos.element.scrollLeft = pos.left;
            pos.element.scrollTop = pos.top;
            requestAnimationFrame(() => {
                pos.element.scrollLeft = pos.left;
                pos.element.scrollTop = pos.top;
            });
        });
    """, positions)


def scroll_by(driver: WebDriver, x: int, y: int, element: WebElement = None) -> None:
    """
    Scroll an element or window by specified distances.
    
    Args:
        driver: WebDriver instance
        x: Horizontal scroll distance in pixels
        y: Vertical scroll distance in pixels
        element: Optional element to scroll. If None, scrolls the window
    """
    if not driver:
        raise ValueError("Driver is not initialized")
    
    driver.execute_script("""
        if (arguments[2]) {
            // Element scroll
            const element = arguments[2];
            const currentLeft = element.scrollLeft;
            const currentTop = element.scrollTop;
            
            element.scrollBy({
                left: arguments[0],
                top: arguments[1],
                behavior: 'auto'
            });
            
            // Verify scroll in next frame
            requestAnimationFrame(() => {
                element.scrollLeft = currentLeft + arguments[0];
                element.scrollTop = currentTop + arguments[1];
            });
        } else {
            // Window scroll
            const currentLeft = window.scrollX;
            const currentTop = window.scrollY;
            
            window.scrollBy({
                left: arguments[0],
                top: arguments[1],
                behavior: 'auto'
            });
            
            // Verify scroll in next frame
            requestAnimationFrame(() => {
                window.scrollTo(currentLeft + arguments[0], currentTop + arguments[1]);
            });
        }
    """, x, y, element)
    

def scroll_element_into_view(driver: WebDriver, element: WebElement, scroll_info: dict[str, Any]) -> None:
    """Scroll element into view based on scroll requirements."""
    if not driver:
        raise ValueError("Driver is not initialized")
    
    driver.execute_script("""
        const info = arguments[0];
        const element = arguments[1];
        
        if (info.needs.horizontal && info.parents.horizontal) {
            const parent = info.parents.horizontal;
            const parentRect = parent.getBoundingClientRect();
            const centerX = (info.elementRect.left + info.elementRect.right) / 2;
            parent.scrollLeft += (centerX - parentRect.width / 2);
        }
        
        if (info.needs.vertical && info.parents.vertical) {
            const parent = info.parents.vertical;
            const parentRect = parent.getBoundingClientRect();
            const centerY = (info.elementRect.top + info.elementRect.bottom) / 2;
            parent.scrollTop += (centerY - parentRect.height / 2);
        }
    """, scroll_info, element)


def scroll_to(driver: WebDriver, x: int, y: int) -> None:
    """Scroll to specific coordinates on the page."""
    if not driver:
        raise ValueError("Driver is not initialized")
        
    driver.execute_script(
        """
        const targetX = arguments[0];
        const targetY = arguments[1];
        
        window.scrollTo({
            left: targetX,
            top: targetY,
            behavior: 'auto'
        });
        
        // Verify scroll position in next frame
        requestAnimationFrame(() => {
            window.scrollTo(targetX, targetY);
        });
        """,
        x,
        y
    )