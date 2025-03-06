import os
from dataclasses import dataclass


@dataclass
class AzureConfig:
    """Azure configuration settings."""
    endpoint: str
    key: str

    @classmethod
    def from_env(cls) -> "AzureConfig":
        """Create configuration from environment variables."""
        endpoint = os.environ.get("AZURE_AI_SERVICES_ENDPOINT")
        key = os.environ.get("AZURE_AI_SERVICES_KEY")
        
        if not endpoint or not key:
            raise ValueError("Azure credentials not found in environment variables")
            
        return cls(endpoint=endpoint, key=key)

@dataclass
class ProcessingConfig:
    """Document processing configuration."""
    min_confidence: float = 0.8
    include_tables: bool = True
    include_figures: bool = True
    clean_text: bool = True
    debug_output: bool = False

    def __post_init__(self):
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")