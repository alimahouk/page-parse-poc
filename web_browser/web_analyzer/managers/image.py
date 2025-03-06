import cv2
import numpy as np
from sklearn.cluster import KMeans


class ImageProcessor:
    """Handles image processing operations."""
    
    @staticmethod
    def detect_hover_changes(
        before_img: np.ndarray,
        after_img: np.ndarray, 
        min_area: int = 500,
        min_dimension: int = 20
    ) -> list[tuple[int, int, int, int]]:
        """Detect regions of change between two images."""
        before_gray = cv2.cvtColor(before_img, cv2.COLOR_RGB2GRAY)
        after_gray = cv2.cvtColor(after_img, cv2.COLOR_RGB2GRAY)
        diff = cv2.absdiff(before_gray, after_gray)
        _, thresh = cv2.threshold(diff, 40, 255, cv2.THRESH_BINARY)
        kernel = np.ones((5,5), np.uint8)
        dilated = cv2.dilate(thresh, kernel, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        regions = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            if area >= min_area and w >= min_dimension and h >= min_dimension:
                regions.append((x, y, x + w, y + h))
        
        return regions
    
    @staticmethod
    def get_dominant_color(img: np.ndarray) -> tuple[int, int, int]:
        """Get the dominant RGB color in an image region."""
        # Check if image is empty
        if img.size == 0:
            raise ValueError("Empty image array provided")

        # Ensure image has valid dimensions
        if len(img.shape) < 3 or img.shape[2] != 3:
            raise ValueError(f"Expected RGB image with shape (H,W,3), got {img.shape}")

        # Reshape and filter out any invalid pixels
        pixels = img.reshape(-1, 3)

        # Add validation check
        if pixels.shape[0] == 0:
            raise ValueError("No valid pixels found in the image")

        # Proceed with clustering
        kmeans = KMeans(n_clusters=1, n_init=1, random_state=42)
        kmeans.fit(pixels)
        return tuple(map(int, kmeans.cluster_centers_[0]))