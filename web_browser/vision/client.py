import logging
import time
from contextlib import contextmanager
from io import BytesIO
from threading import Lock
from typing import Optional

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
from filelock import FileLock
from openai import AzureOpenAI
from PIL import Image

from web_browser.vision.config import OpenAIConfig, VisionConfig
from web_browser.vision.models import ImageAnalysisResult
from web_browser.vision.types import WebpageDescription
from web_browser.vision.utils import encode_image

logger = logging.getLogger(__name__)

class VisionAnalysisClient:
    """Client for handling both Azure Vision and OpenAI vision analysis."""
    
    def __init__(
        self, 
        vision_config: VisionConfig,
        openai_config: Optional[OpenAIConfig] = None
    ):
        self.openai_client = None
        self.openai_config = openai_config
        if openai_config:
            self.openai_client = AzureOpenAI(
                api_key=openai_config.api_key,
                api_version=openai_config.api_version,
                azure_endpoint=openai_config.endpoint
            )
        
        self.vision_client = ImageAnalysisClient(
            endpoint=vision_config.endpoint,
            credential=AzureKeyCredential(vision_config.key)
        )

        # Add rate limiting
        self._openai_lock = Lock()
        self._vision_lock = Lock()
        self._last_openai_call = 0
        self._last_vision_call = 0
        self.openai_rate_limit = 0.5  # seconds between calls
        self.vision_rate_limit = 1.0  # seconds between calls

    def analyze_image(self, image_data: BytesIO) -> Optional[ImageAnalysisResult]:
        try:
            self._wait_for_vision_rate_limit()
            
            with Image.open(image_data) as img:
                width, height = img.size
                if width < 50 or height < 50 or width > 16000 or height > 16000:
                    raise ValueError(f"Invalid image dimensions: {width}x{height}")
                
                result = self.vision_client.analyze(
                    image_data=image_data.getvalue(),
                    visual_features=[VisualFeatures.CAPTION, VisualFeatures.READ],
                )
    
                return ImageAnalysisResult(
                    caption=result.caption.text if result.caption else None,
                    detected_text="\n".join(
                        line.text 
                        for block in result.read.blocks 
                        for line in block.lines
                    ) if result.read and result.read.blocks else None
                )
    
        except Exception as e:
            raise ValueError(f"Failed to analyze image: {str(e)}")
    
    @contextmanager
    def _file_access(self, filename: str):
        lock = FileLock(f"{filename}.lock")
        with lock:
            try:
                yield
            finally:
                if lock.is_locked:
                    lock.release()

    @classmethod
    def from_env(cls) -> "VisionAnalysisClient":
        """Create client using environment variables."""
        vision_config = VisionConfig.from_env()
        try:
            openai_config = OpenAIConfig.from_env()
        except ValueError:
            openai_config = None
        return cls(vision_config, openai_config)

    def describe_image_for_accessibility(self, filename: str) -> Optional[str]:
        """
        Get an accessibility-focused description of an image using Azure OpenAI.
        
        Args:
            filename: Path to the image file
            
        Returns:
            String containing the accessibility description
            
        Raises:
            ValueError: If OpenAI client is not configured or for API errors
        """
        if not filename:
            raise ValueError("Filename cannot be None or empty")
        
        if not self.openai_client:
            raise ValueError("OpenAI client not configured")

        try:
            base64_image = encode_image(filename)

            response = self.openai_client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe this screenshot like you would to someone who is visually impaired.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                model=self.openai_config.model,
            )
            return response.choices[0].message.content
            
        except Exception as e:
            raise ValueError(f"Failed to generate accessibility description: {str(e)}")
    
    def describe_screenshot(self, filename: str) -> Optional[WebpageDescription]:
        """
        Generate a structured description of a webpage screenshot that can be used
        for automated interaction.
        
        Args:
            filename: Path to the image file
                
        Returns:
            WebpageDescription object containing the structured description
                
        Raises:
            ValueError: If OpenAI client is not configured or for API errors
        """
        if not filename:
            raise ValueError("Filename cannot be None or empty")
        
        if not self.openai_client:
            raise ValueError("OpenAI client not configured")
    
        try:
            base64_image = encode_image(filename)
            completion = self.openai_client.beta.chat.completions.parse(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing webpage screenshots and describing them in a way that helps AI systems locate and interact with elements. Focus on precision in describing locations and interactive elements. Use clear, consistent terms for positions (top, bottom, left, right, center) and measurements.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze this webpage screenshot and provide a structured description that can help locate and interact with elements.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                model=self.openai_config.model,
                response_format=WebpageDescription,
            )
            description = completion.choices[0].message

            if (description.refusal):
                logger.warning(description.refusal)
            else:
                return description.parsed
        
        except Exception as e:
            raise ValueError(f"Failed to generate screenshot description: {str(e)}")
    
    def _wait_for_vision_rate_limit(self):
        with self._vision_lock:
            now = time.time()
            if now - self._last_vision_call < self.vision_rate_limit:
                time.sleep(self.vision_rate_limit - (now - self._last_vision_call))
            self._last_vision_call = time.time()