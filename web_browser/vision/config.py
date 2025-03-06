import os
from dataclasses import dataclass


@dataclass
class VisionConfig:
    """Azure Vision API configuration."""
    endpoint: str
    key: str

    @classmethod
    def from_env(cls) -> "VisionConfig":
        """Create configuration from environment variables."""
        endpoint = os.environ.get("AZURE_AI_SERVICES_ENDPOINT")
        key = os.environ.get("AZURE_AI_SERVICES_KEY")
        
        if not endpoint or not key:
            raise ValueError("Azure Vision credentials not found in environment variables")
            
        return cls(endpoint=endpoint, key=key)

@dataclass
class OpenAIConfig:
    """Azure OpenAI configuration."""
    api_key: str
    api_version: str
    endpoint: str
    model: str = "gpt-4o"

    @classmethod
    def from_env(cls) -> "OpenAIConfig":
        """Create configuration from environment variables."""
        api_key = os.environ.get("OPENAI_API_KEY")
        api_version = os.environ.get("OPENAI_API_VERSION")
        endpoint = os.environ.get("OPENAI_API_ENDPOINT")
        
        if not all([api_key, api_version, endpoint]):
            raise ValueError("Azure OpenAI credentials not found in environment variables")
            
        return cls(
            api_key=api_key,
            api_version=api_version,
            endpoint=endpoint
        )