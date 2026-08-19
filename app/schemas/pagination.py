from collections.abc import Sequence

from pydantic import BaseModel, Field


class PaginatedResponse[T](BaseModel):
    """Standardized paginated response envelope."""

    items: Sequence[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=1000)
    offset: int = Field(ge=0)
    has_more: bool
