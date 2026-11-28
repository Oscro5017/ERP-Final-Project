"""Suggestions for names of things used in activities."""
from datetime import datetime

from .common import DecryptionStatusResponse


class InputCatalogSuggestionResponse(DecryptionStatusResponse):
    id: int
    item_name: str
    last_unit: str | None = None
    last_category: str | None = None
    last_used_at: datetime | None = None
    use_count: int
    product_id: int | None = None


class InputCatalogSuggestionsResponse(DecryptionStatusResponse):
    items: list[InputCatalogSuggestionResponse]
    is_masked: bool
