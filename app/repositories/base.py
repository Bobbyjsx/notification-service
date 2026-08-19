from typing import Any

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel


class BaseRepository[T: BaseModel]:
    """Base repository providing standardized async Firestore operations."""

    def __init__(self, db: AsyncClient, collection_name: str, model_class: type[T]) -> None:
        self.db = db
        self.collection_name = collection_name
        self.model_class = model_class

    @property
    def collection(self):
        return self.db.collection(self.collection_name)

    async def get_by_id(self, doc_id: str) -> T | None:
        """Fetch a document by its ID."""
        doc_ref = self.collection.document(doc_id)
        doc = await doc_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        data["id"] = doc.id
        return self.model_class(**data)

    async def create(self, item: T) -> T:
        """Create or set a document using its internal ID."""
        data = item.model_dump(mode="json")
        doc_id = data.get("id")
        if not doc_id:
            raise ValueError("Item must have an id field for persistence")
        doc_ref = self.collection.document(str(doc_id))
        await doc_ref.set(data)
        return item

    async def update(self, doc_id: str, updates: dict[str, Any]) -> None:
        """Update specific fields in a document."""
        doc_ref = self.collection.document(doc_id)
        await doc_ref.update(updates)

    async def delete(self, doc_id: str) -> None:
        """Delete a document by ID."""
        doc_ref = self.collection.document(doc_id)
        await doc_ref.delete()

    async def find_one_by_field(self, field_name: str, value: Any) -> T | None:
        """Find the first matching document by an exact field equality filter."""
        query = self.collection.where(filter=FieldFilter(field_name, "==", value)).limit(1)
        docs = query.stream()
        async for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            return self.model_class(**data)
        return None
