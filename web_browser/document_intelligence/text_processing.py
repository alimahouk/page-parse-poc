import unicodedata


def normalize_text(text: str, preserve_newlines: bool = True) -> str:
    """
    Clean and normalize text while preserving valid characters.
    
    Args:
        text: Text to normalize
        preserve_newlines: Whether to preserve line breaks in output
        
    Returns:
        Normalized text string
    """
    if not text:
        return ""
        
    # Normalize Unicode (NFC form for composed characters)
    text = unicodedata.normalize("NFC", text)
    
    # Remove control chars but keep newlines and tabs
    text = "".join(char for char in text 
                  if unicodedata.category(char)[0] != "C" 
                  or char in "\n\t")
    
    # Normalize whitespace
    lines = text.splitlines()
    cleaned_lines = [" ".join(line.split()) for line in lines]
    
    if preserve_newlines:
        return "\n".join(line for line in cleaned_lines if line)
    return " ".join(line for line in cleaned_lines if line)