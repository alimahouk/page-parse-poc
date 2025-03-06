from typing import Optional, TypedDict


class Position(TypedDict):
    """Represents an element's position and dimensions."""
    height: int
    width: int
    x: int
    y: int


class Visibility(TypedDict):
    """Represents an element's visibility properties."""
    display: str
    opacity: str
    visibility: str


class ElementProperties(TypedDict):
    """Properties of a DOM element."""
    href: Optional[str]
    position: Position
    selector: str
    src: Optional[str]
    tagName: str
    text: str
    visibility: Visibility


class DOMNode(TypedDict):
    """A node in the DOM tree."""
    children: list["DOMNode"]
    properties: ElementProperties


class DOMTree(TypedDict):
    """The complete DOM tree structure."""
    children: list[DOMNode]
    type: str