from dataclasses import dataclass


@dataclass
class Config:
    """Configuration for element analysis."""
    detect_hover: bool = True
    min_height: int = 11
    min_size: int = 50
    min_width: int = 11
    parse_delay: float = 30.0
    screenshot_dir: str = "ui"
    timeout: int = 10
    viewport_only: bool = True
    wait_for_network_idle: bool = False