"""Content chunker — splits long text into overlapping chunks for IdeaBlock extraction.

Blockify ingest spec:
  - Chunk size : 1-4K characters (we default to 2000)
  - Overlap    : ~10% of chunk size (200 chars) to preserve context at boundaries
  - Short text : returned as-is in a single-element list (no splitting)

Split strategy:
  1. Try to break at paragraph boundaries (double newline) within ±200 chars of the split point.
  2. Fall back to sentence boundary (". ") if no paragraph boundary found.
  3. Hard split at character boundary as last resort.
"""

from __future__ import annotations

_DEFAULT_MAX_CHARS = 2000
_DEFAULT_OVERLAP_CHARS = 200  # 10% of 2000
_BOUNDARY_SEARCH_WINDOW = 200


class ContentChunker:
    """Splits raw text into overlapping fixed-size chunks.

    Designed to feed each chunk into an LLM for IdeaBlock extraction
    without exceeding the model's practical context capacity.
    """

    def __init__(
        self,
        max_chars: int = _DEFAULT_MAX_CHARS,
        overlap_chars: int = _DEFAULT_OVERLAP_CHARS,
    ) -> None:
        self._max = max_chars
        self._overlap = overlap_chars

    def chunk(self, text: str) -> list[str]:
        """Return a list of overlapping text chunks.

        Short text (≤ max_chars) is returned as a single element.
        """
        text = text.strip()
        if not text:
            return []
        if len(text) <= self._max:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = min(start + self._max, len(text))

            # Try to break at a natural boundary if we're not at the end
            if end < len(text):
                end = self._find_split_point(text, end)

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= len(text):
                break

            # Next chunk starts with overlap to preserve boundary context
            start = max(start + 1, end - self._overlap)

        return chunks

    def _find_split_point(self, text: str, ideal_end: int) -> int:
        """Find the nearest natural boundary within a search window."""
        window_start = max(0, ideal_end - _BOUNDARY_SEARCH_WINDOW)
        window_end = min(len(text), ideal_end + _BOUNDARY_SEARCH_WINDOW)
        segment = text[window_start:window_end]

        # Prefer paragraph break (double newline)
        para_idx = segment.rfind("\n\n")
        if para_idx >= 0:
            return window_start + para_idx + 2

        # Fall back to sentence boundary
        sent_idx = segment.rfind(". ")
        if sent_idx >= 0:
            return window_start + sent_idx + 2

        # Hard split at ideal position
        return ideal_end
