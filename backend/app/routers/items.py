"""Example CRUD router. Copy this file as the starting point for a new resource."""

from fastapi import APIRouter, HTTPException, status

from app.crud.item import item_crud
from app.schemas.item import Item, ItemCreate, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


def _not_found(item_id: int) -> HTTPException:
    """Build the 404 raised when `item_id` does not exist."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")


@router.get("")
async def list_items() -> list[Item]:
    """Return every item."""
    return item_crud.list()


@router.get("/{item_id}")
async def get_item(item_id: int) -> Item:
    """Return a single item."""
    item = item_crud.get(item_id)
    if item is None:
        raise _not_found(item_id)
    return item


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate) -> Item:
    """Create an item."""
    return item_crud.create(payload)


@router.patch("/{item_id}")
async def update_item(item_id: int, payload: ItemUpdate) -> Item:
    """Partially update an item."""
    item = item_crud.update(item_id, payload)
    if item is None:
        raise _not_found(item_id)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int) -> None:
    """Delete an item."""
    if not item_crud.delete(item_id):
        raise _not_found(item_id)
