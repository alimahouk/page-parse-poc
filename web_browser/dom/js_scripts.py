"""JavaScript functions used for DOM manipulation."""

GET_ELEMENT_PROPERTIES_SCRIPT = """
function getElementProperties(elem) {
    if (!elem || typeof elem !== 'object') {
        return null;
    }
    
    // Safely get tag name
    const tagName = (elem.tagName && typeof elem.tagName.toLowerCase === 'function') 
        ? elem.tagName.toLowerCase() 
        : '';
    
    // Safely get bounding rect
    let rect;
    try {
        rect = elem.getBoundingClientRect();
    } catch (e) {
        rect = { left: 0, top: 0, width: 0, height: 0 };
    }
    
    // Enhanced text content extraction
    let text = '';
    
    // Handle input elements
    if (tagName === 'input') {
        text = elem.placeholder || elem.value || '';
    }
    // Handle images
    else if (tagName === 'img') {
        text = elem.alt || elem.title || '';
    }
    // Handle other elements
    else {
        // Get direct text content
        const walker = document.createTreeWalker(
            elem,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function(node) {
                    return node.parentNode === elem ? 
                        NodeFilter.FILTER_ACCEPT : 
                        NodeFilter.FILTER_REJECT;
                }
            }
        );
        
        let node;
        while (node = walker.nextNode()) {
            const trimmed = node.textContent.trim();
            if (trimmed) {
                text += (text ? ' ' : '') + trimmed;
            }
        }
        
        // Fallback to aria-label or other attributes
        if (!text) {
            text = elem.getAttribute('aria-label') ||
                  elem.getAttribute('title') ||
                  '';
        }
    }
    
    // Get CSS properties that affect visibility
    const style = window.getComputedStyle(elem);
    
    return {
        tagName: tagName,
        text: text,
        href: elem.href || null,
        src: elem.src || elem.getAttribute('src') || null,
        position: {
            x: Math.round(rect.left),
            y: Math.round(rect.top),
            width: Math.round(rect.width),
            height: Math.round(rect.height)
        },
        visibility: {
            display: style.display,
            visibility: style.visibility,
            opacity: style.opacity
        },
        selector: getUniqueSelector(elem)
    };
}

function getUniqueSelector(elem) {
    if (!elem || typeof elem !== 'object') {
        return '';
    }
    
    if (elem.id) return '#' + elem.id;
    
    let path = [];
    while (elem && elem.nodeType === 1) {  // Check for Element node type
        if (elem.id) {
            path.unshift('#' + elem.id);
            break;
        }
        
        let selector = elem.tagName.toLowerCase();
        let siblings = Array.from(elem.parentNode?.children || [])
            .filter(e => e.tagName === elem.tagName);
            
        if (siblings.length > 1) {
            let index = siblings.indexOf(elem) + 1;
            selector += `:nth-child(${index})`;
        }
        
        path.unshift(selector);
        elem = elem.parentNode;
        
        if (!elem || elem === document.body) break;
    }
    
    return path.join(' > ');
}

return getElementProperties(arguments[0]);
"""