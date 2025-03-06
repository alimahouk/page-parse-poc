from typing import Optional

from pydantic import BaseModel


class InteractiveElement(BaseModel):
    type: str  # button, link, input, dropdown, etc
    location: str  # precise location description
    visuals: str  # color, size, icons, etc
    text: Optional[str]  # visible text if any
    purpose: str  # likely function
    state: Optional[str]  # enabled/disabled/selected/etc


class ImageElement(BaseModel):
    location: str
    content: str
    purpose: str


class LayoutSection(BaseModel):
    header: Optional[str]
    main_content: str
    navigation: Optional[str]
    sidebar: Optional[str]


class VisualHierarchy(BaseModel):
    primary_focus: str
    secondary_elements: list[str]
    background_elements: list[str]


class KeyContent(BaseModel):
    headings: list[str]
    main_text_blocks: list[str]
    images: list[ImageElement]


class WebpageDescription(BaseModel):
    layout: LayoutSection
    interactive_elements: list[InteractiveElement]
    key_content: KeyContent
    visual_hierarchy: VisualHierarchy