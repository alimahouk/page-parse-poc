import logging
from typing import Optional, Union

import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from web_browser.web_analyzer.elements.unified_element import UnifiedElement
from web_browser.web_analyzer.types import PageRegion, RegionBounds

logger = logging.getLogger(__name__)

class ElementSearchSystem:
    def __init__(self):
        self._element_lookup: dict[str, UnifiedElement] = {}
        self._embeddings: Optional[torch.Tensor] = None
        self._ids: list[str] = []

        self._device = (
            "mps"
            if torch.backends.mps.is_available()
            else "cuda" if torch.cuda.is_available() else "cpu"
        )
        # Using a larger model that's better at semantic search
        self.model = SentenceTransformer("thenlper/gte-large").to(self._device)

        # Load reranker
        self._reranker_tokenizer = AutoTokenizer.from_pretrained(
            "BAAI/bge-reranker-v2-m3"
        )
        self._reranker_model = (
            AutoModelForSequenceClassification.from_pretrained(
                "BAAI/bge-reranker-v2-m3"
            ).to(self._device)
        )
        self._reranker_model.eval()

    def _create_embedding_text(self, element: UnifiedElement) -> str:
        if not element:
            raise ValueError("Expected a UnifiedElement instance")

        parts = []

        # Preserve original content with case
        if element.content:
            parts.append(element.content)

        # Add image caption if available
        if element.image_caption:
            parts.append(f"image showing {element.image_caption}")

        # Add hover text if different from original content
        if element.hover_state and element.hover_state.get("text_after"):
            hover_text = element.hover_state["text_after"]
            if hover_text != element.content:
                parts.append(f"reveals {hover_text} on hover")

        # Core purpose/action of the element
        if element.element_type == "clickable":
            if element.tag in ["button", "input"]:
                parts.append("button")
                if element.content:
                    parts.append(f"clickable button {element.content}")
            elif element.tag == "a":
                parts.append("link")
                if element.content:
                    parts.append(f"clickable link {element.content}")
                if element.href:
                    # Clean up URL text for better semantic matching
                    href_text = element.href.replace("-", " ").replace("_", " ")
                    parts.append(f"links to {href_text}")

        # Interactive properties with context
        if (
            element.hover_state
            and element.hover_state.get("cursor_style") == "pointer"
        ):
            parts.append("interactive clickable element")

        # Visibility with context
        if element.visibility:
            if element.visibility.get("display") not in ["none", "hidden"]:
                parts.append("visible element on page")

        # Join with spaces and avoid double spaces
        return " ".join(parts).strip()

    def index_elements(self, elements: list[UnifiedElement]) -> None:
        """
        Index elements if no current index exists.
        """
        if self._embeddings is not None:
            logger.info("Index already exists, skipping reindex")
            return

        self._ids = [str(i) for i in range(len(elements))]
        self._element_lookup = {
            id_: elem for id_, elem in zip(self._ids, elements)
        }

        contents = [self._create_embedding_text(elem) for elem in elements]

        # Ensure L2 normalization for more stable similarity scores
        self._embeddings = self.model.encode(
            contents,
            convert_to_tensor=True,
            device=self._device,
            normalize_embeddings=True,
        )

    def invalidate_index(self) -> None:
        """
        Explicitly invalidate the current index, forcing a reindex on next use.
        """
        self._embeddings = None
        self._element_lookup.clear()
        self._ids.clear()

    def search(
        self, query: str, n: int = 10, rerank_top_k: int = 5
    ) -> list[tuple[UnifiedElement, float]]:
        if not query:
            raise ValueError("Expected a non-empty query")

        query = query.strip()

        if self._embeddings is None:
            return []

        # Initial retrieval with normalized embeddings
        query_embedding = self.model.encode(
            [query],
            convert_to_tensor=True,
            device=self._device,
            normalize_embeddings=True,
        )

        # Use scaled cosine similarity for better score distribution
        similarities = (
            torch.nn.functional.cosine_similarity(
                query_embedding, self._embeddings
            )
            / 0.07
        )

        # Get top-n results
        top_n = min(n, len(self._ids))
        top_indices = torch.argsort(similarities, descending=True)[:top_n]
        initial_results = [
            (self._ids[i.item()], similarities[i].item()) for i in top_indices
        ]

        # Reranking with cross-attention for better semantic matching
        if rerank_top_k > 0 and initial_results:
            pairs = [
                [
                    query,
                    self._create_embedding_text(
                        self._element_lookup[result_id]
                    ),
                ]
                for result_id, _ in initial_results
            ]

            inputs = self._reranker_tokenizer(
                pairs,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=512,
            ).to(self._device)

            with torch.no_grad():
                scores = self._reranker_model(**inputs).logits.view(-1)
                scores = torch.nn.functional.softmax(scores, dim=0)

            # Combine initial and reranking scores with weighted average
            alpha = 0.7  # Weight for reranker scores
            reranked = [
                (
                    initial_results[i][0],
                    alpha * scores[i].item()
                    + (1 - alpha) * initial_results[i][1],
                )
                for i in range(len(scores))
            ]

            final_results = [
                (self._element_lookup[id_], score)
                for id_, score in sorted(
                    reranked, key=lambda x: x[1], reverse=True
                )[:rerank_top_k]
            ]
        else:
            final_results = [
                (self._element_lookup[id_], score)
                for id_, score in initial_results
            ]

        return final_results

    def search_by_region(
        self, region: Union[PageRegion, set[PageRegion]]
    ) -> list[UnifiedElement]:
        """
        Find all elements within a specified region of the page.

        Args:
            region: Either a single PageRegion or set of PageRegions to search within

        Returns:
            List of UnifiedElements that fall within the specified region
        """
        if not self._element_lookup:
            return []

        # Get page dimensions from first element's bounding box
        # Assuming the first element has valid bounds
        first_elem = next(iter(self._element_lookup.values()))
        if not first_elem.bounding_box:
            return []

        # Find maximum bounds from all elements to determine page size
        page_width = max(
            elem.bounding_box.right
            for elem in self._element_lookup.values()
            if elem.bounding_box
        )
        page_height = max(
            elem.bounding_box.bottom
            for elem in self._element_lookup.values()
            if elem.bounding_box
        )

        bounds = RegionBounds.from_page_dimensions(
            page_width, page_height, region
        )

        matching_elements = []
        for element in self._element_lookup.values():
            if not element.bounding_box:
                continue

            bb = element.bounding_box

            # Check if element is fully contained within the region
            is_within_region = (
                bb.left >= bounds.left
                and bb.top >= bounds.top
                and bb.right <= bounds.right
                and bb.bottom <= bounds.bottom
            )

            # Or check if element significantly overlaps with the region
            if not is_within_region:
                overlap_left = max(bounds.left, bb.left)
                overlap_top = max(bounds.top, bb.top)
                overlap_right = min(bounds.right, bb.right)
                overlap_bottom = min(bounds.bottom, bb.bottom)

                if (
                    overlap_left < overlap_right
                    and overlap_top < overlap_bottom
                ):
                    overlap_area = (overlap_right - overlap_left) * (
                        overlap_bottom - overlap_top
                    )
                    element_area = bb.width * bb.height

                    # Consider elements with >50% overlap
                    is_within_region = overlap_area > (element_area * 0.5)

            if is_within_region:
                matching_elements.append(element)

        # Sort elements by their vertical position (top to bottom)
        return sorted(matching_elements, key=lambda e: e.bounding_box.top)
