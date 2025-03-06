import base64


def encode_image(filename: str) -> str:
    """Encode an image file as base64."""
    try:
        with open(filename, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to encode image: {str(e)}")