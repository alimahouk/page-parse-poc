import os
from collections import defaultdict
from typing import Optional

from azure.ai.documentintelligence import models as _models
from azure.ai.documentintelligence.models import (AnalyzeResult,
                                                  DocumentAnalysisFeature,
                                                  DocumentFigure, DocumentLine,
                                                  DocumentPage, DocumentTable,
                                                  DocumentWord)

from web_browser.document_intelligence.client import DocumentClient
from web_browser.document_intelligence.config import ProcessingConfig
from web_browser.document_intelligence.models import (FigureInfo, OCRElement,
                                                      OCRLine, TableInfo)
from web_browser.document_intelligence.text_processing import normalize_text
from web_browser.document_intelligence.utils import get_words, print_page_info


class DocumentProcessor:
    """Handles document analysis and OCR processing."""
    
    def __init__(self, client: DocumentClient, config: ProcessingConfig):
        self.client = client
        self.config = config
        
    def analyze_layout(
        self, 
        filename: str
    ) -> tuple[list[OCRElement], list[TableInfo], list[FigureInfo]]:
        """
        Analyze document layout including text, tables, and figures.
        
        Args:
            filename: Path to the image file to analyze
            
        Returns:
            Tuple containing processed OCR elements, tables, and figures
            
        Raises:
            FileNotFoundError: If image file doesn't exist
            Exception: For Azure API or processing errors
        """
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Image file not found: {filename}")

        try:
            result = self._analyze_document(filename, "prebuilt-layout")
            
            ocr_elements, tables, figures = [], [], []
            stats = defaultdict(int)

            for page in result.pages:
                print_page_info(page)
                
                # Process text
                page_elements = self._process_page_text(page)
                ocr_elements.extend(page_elements)
                stats["total_words"] += len(page_elements)

                # Process tables
                if self.config.include_tables and result.tables:
                    self._process_page_tables(page, result.tables, tables, stats)

                # Process figures
                if self.config.include_figures and result.figures:
                    self._process_page_figures(page, result.figures, figures, stats)

            self._print_analysis_summary(stats)
            return ocr_elements, tables, figures

        except Exception as e:
            print(f"ERROR: Document analysis failed: {str(e)}")
            raise

    def analyze_read(self, filename: str) -> list[OCRLine]:
        """
        Analyze document and return OCR results at the line level.
        
        Args:
            filename: Path to the image file to analyze
            
        Returns:
            List of processed OCR lines meeting confidence threshold
        
        Raises:
            FileNotFoundError: If image file doesn't exist
            Exception: For Azure API or processing errors
        """
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Image file not found: {filename}")

        try:
            result = self._analyze_document(filename, "prebuilt-read")
            
            ocr_lines: list[OCRLine] = []
            total_stats = {"total_words": 0, "filtered_words": 0}

            for page in result.pages:
                print_page_info(page)
                page_lines, page_stats = self._process_page_lines(page)
                ocr_lines.extend(page_lines)
                
                total_stats["total_words"] += page_stats["total_words"]
                total_stats["filtered_words"] += page_stats["filtered_words"]

            if self.config.debug_output:
                self._print_ocr_summary(total_stats, len(ocr_lines))
            
            return ocr_lines
            
        except Exception as e:
            print(f"ERROR: OCR processing failed: {str(e)}")
            raise

    def _analyze_document(self, filename: str, model: str) -> AnalyzeResult:
        """Perform document analysis using Azure client."""
        with open(filename, "rb") as f:
            document_bytes = f.read()

            # Create the analyze request object with raw bytes
            request = _models.AnalyzeDocumentRequest(
                bytes_source=document_bytes
            )

            poller = self.client.client.begin_analyze_document(
                model_id=model,
                body=request,
                features=[DocumentAnalysisFeature.LANGUAGES],
                content_type="application/json"
            )
        return poller.result()

    def _print_analysis_summary(self, stats: dict[str, int]) -> None:
        """Print summary of document analysis results."""
        print("\nDocument Analysis Summary:")
        print(f"Total words processed: {stats['total_words']}")
        if self.config.include_tables:
            print(f"Tables found: {stats['tables']}")
            print(f"Table cells processed: {stats['table_cells']}")
        if self.config.include_figures:
            print(f"Figures found: {stats['figures']}")
        print("----------------------------------------")

    def _print_ocr_summary(
        self, 
        stats: dict[str, int], 
        total_lines: int
    ) -> None:
        """Print summary of OCR processing results."""
        print("\nOCR Processing Summary:")
        print(f"Total words processed: {stats['total_words']}")
        print(f"Words filtered (confidence < {self.config.min_confidence}): {stats['filtered_words']}")
        print(f"Lines extracted: {total_lines}")
        print("----------------------------------------")

    def _process_figure(
        self, 
        figure: DocumentFigure
    ) -> Optional[FigureInfo]:
        """Process a single figure's information."""
        if not figure.bounding_regions:
            return None
            
        region = figure.bounding_regions[0]
        return FigureInfo(
            page_number=region.page_number,
            polygon=region.polygon,
            spans=figure.spans
        )
    
    def _process_line(
        self,
        line: DocumentLine,
        words: list[DocumentWord],
        line_idx: int,
        page_number: int
    ) -> tuple[Optional[OCRLine], dict[str, int]]:
        """Process a line of text and return OCRLine object and statistics."""
        stats = {"processed": 0, "filtered": 0}
        processed_words: list[tuple[str, float]] = []
        word_confidences: list[float] = []
        
        for word in words:
            stats["processed"] += 1
            content, confidence = self._process_word(word)
            
            if content:
                processed_words.append((content, confidence))
                word_confidences.append(confidence)
            else:
                stats["filtered"] += 1
                if self.config.debug_output and confidence < self.config.min_confidence:
                    print(f"......Filtered low confidence word: '{word.content}' ({confidence:.2f})")
        
        if not processed_words:
            return None, stats
            
        avg_confidence = sum(word_confidences) / len(word_confidences)
        if avg_confidence < self.config.min_confidence:
            if self.config.debug_output:
                print(f"...Filtered low confidence line {line_idx}")
            return None, stats
            
        line_content = line.content
        if self.config.clean_text:
            line_content = normalize_text(line_content)
            
        ocr_line = OCRLine(
            content=line_content,
            confidence=avg_confidence,
            polygon=line.polygon,
            words=processed_words,
            page_number=page_number
        )
        
        if self.config.debug_output:
            print(
                f"...Line {line_idx}: {len(processed_words)} words, "
                f"confidence {avg_confidence:.2f}, "
                f"text: {repr(line_content)}"
            )
            
        return ocr_line, stats
    
    def _process_page_text(self, page: DocumentPage) -> list[OCRElement]:
        """Process text elements from a single page."""
        elements = []
        
        if not page.lines:
            return elements
            
        for line in page.lines:
            words = get_words(page, line)
            for word in words:
                if word.confidence >= self.config.min_confidence:
                    cleaned_content = normalize_text(
                        word.content, 
                        preserve_newlines=False
                    ) if self.config.clean_text else word.content
                    
                    if cleaned_content.strip():
                        elements.append(OCRElement(
                            content=cleaned_content,
                            confidence=word.confidence,
                            polygon=word.polygon,
                            span=word.span,
                            page_number=page.page_number
                        ))
                    
        return elements

    def _process_page_figures(
        self,
        page: DocumentPage,
        all_figures: list[DocumentFigure],
        figures: list[FigureInfo],
        stats: dict[str, int]
    ) -> None:
        """Process figures from a single page."""
        page_figures = [
            figure for figure in all_figures
            if any(region.page_number == page.page_number 
                  for region in figure.bounding_regions)
        ]
        
        for figure in page_figures:
            if figure_info := self._process_figure(figure):
                figures.append(figure_info)
                stats["figures"] += 1

    def _process_page_lines(
        self, 
        page: DocumentPage
    ) -> tuple[list[OCRLine], dict[str, int]]:
        """Process a single page and return OCR lines and statistics."""
        page_lines: list[OCRLine] = []
        stats = {"total_words": 0, "filtered_words": 0}
        
        if not page.lines:
            return page_lines, stats
            
        for line_idx, line in enumerate(page.lines):
            words = get_words(page, line)
            ocr_line, line_stats = self._process_line(
                line, words, line_idx, page.page_number
            )
            
            stats["total_words"] += line_stats["processed"]
            stats["filtered_words"] += line_stats["filtered"]
            
            if ocr_line:
                page_lines.append(ocr_line)
                
        return page_lines, stats

    def _process_page_tables(
        self, 
        page: DocumentPage,
        all_tables: list[DocumentTable],
        tables: list[TableInfo],
        stats: dict[str, int]
    ) -> None:
        """Process tables from a single page."""
        page_tables = [
            table for table in all_tables
            if any(region.page_number == page.page_number 
                  for region in table.bounding_regions)
        ]
        
        for table in page_tables:
            table_info = self._process_table(table, page.page_number)
            tables.append(table_info)
            stats["tables"] += 1
            stats["table_cells"] += len(table_info.cells)

    def _process_table(
        self, 
        table: DocumentTable, 
        page_number: int
    ) -> TableInfo:
        """Process a single table's information."""
        cells_info = []
        
        for cell in table.cells:
            cell_info = {
                "row": cell.row_index,
                "col": cell.column_index,
                "content": normalize_text(cell.content) if self.config.clean_text else cell.content,
                "polygon": cell.bounding_regions[0].polygon if cell.bounding_regions else None
            }
            cells_info.append(cell_info)
            
        table_polygon = (table.bounding_regions[0].polygon 
                        if table.bounding_regions else [])
        
        return TableInfo(
            row_count=table.row_count,
            column_count=table.column_count,
            page_number=page_number,
            polygon=table_polygon,
            cells=cells_info
        )
    
    def _process_word(
        self, 
        word: DocumentWord
    ) -> tuple[Optional[str], float]:
        """Process a single word and return cleaned content and confidence."""
        if word.confidence < self.config.min_confidence:
            return None, word.confidence
            
        content = word.content
        if self.config.clean_text:
            content = normalize_text(content, preserve_newlines=False)
            
        return (content.strip(), word.confidence) if content.strip() else (None, word.confidence)