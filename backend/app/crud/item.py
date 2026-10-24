"""CRUD store for the example `items` resource."""

from app.crud.base import InMemoryCRUD
from app.schemas.item import Item, ItemCreate, ItemUpdate

item_crud = InMemoryCRUD[Item, ItemCreate, ItemUpdate](Item)
