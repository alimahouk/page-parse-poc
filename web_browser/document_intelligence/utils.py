from typing import Any

from azure.ai.documentintelligence.models import (DocumentLine, DocumentPage,
                                                  DocumentWord)


def get_words(page: DocumentPage, line: DocumentLine) -> list[DocumentWord]:
    """Get words that fall within a line's span."""
    return [
        word for word in page.words
        if any(spans_overlap(word.span, span) for span in line.spans)
    ]

def spans_overlap(word_span: Any, line_span: Any) -> bool:
    """Check if a word's span overlaps with a line's span."""
    word_start = word_span.offset
    word_end = word_span.offset + word_span.length
    line_start = line_span.offset
    line_end = line_span.offset + line_span.length
    
    return (word_start >= line_start and word_start < line_end) or \
           (word_end > line_start and word_end <= line_end) or \
           (word_start <= line_start and word_end >= line_end)

def print_page_info(page: DocumentPage) -> None:
    """Print standardized page information."""
    print(f"----Analyzing document from page #{page.page_number}----")
    print(f"Page dimensions: {page.width}x{page.height} {page.unit}")