from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

from web_browser.document_intelligence.config import AzureConfig


class DocumentClient:
    """Wrapper for Azure Document Intelligence client."""
    
    def __init__(self, config: AzureConfig):
        self.client = DocumentIntelligenceClient(
            endpoint=config.endpoint,
            credential=AzureKeyCredential(config.key)
        )

    @classmethod
    def from_env(cls) -> "DocumentClient":
        """Create client using environment variables."""
        return cls(AzureConfig.from_env())