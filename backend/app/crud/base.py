"""Generic in-memory CRUD store. Swap for a database-backed class with the same methods."""

from pydantic import BaseModel


class InMemoryCRUD[ModelT: BaseModel, CreateT: BaseModel, UpdateT: BaseModel]:
    """Create, read, update and delete Pydantic models keyed by an auto-incrementing id."""

    def __init__(self, model: type[ModelT]) -> None:
        """Create an empty store that builds instances of `model`."""
        self._model = model
        self._records: dict[int, ModelT] = {}
        self._next_id = 1

    def list(self) -> list[ModelT]:
        """Return every record in insertion order."""
        return list(self._records.values())

    def get(self, record_id: int) -> ModelT | None:
        """Return the record with `record_id`, or None if it does not exist."""
        return self._records.get(record_id)

    def create(self, data: CreateT) -> ModelT:
        """Store a new record built from `data` and return it."""
        record = self._model(id=self._next_id, **data.model_dump())
        self._records[self._next_id] = record
        self._next_id += 1
        return record

    def update(self, record_id: int, data: UpdateT) -> ModelT | None:
        """Apply the fields set on `data` to a record and return it, or None if missing."""
        record = self._records.get(record_id)
        if record is None:
            return None
        updated = record.model_copy(update=data.model_dump(exclude_unset=True))
        self._records[record_id] = updated
        return updated

    def delete(self, record_id: int) -> bool:
        """Remove a record, returning whether it existed."""
        return self._records.pop(record_id, None) is not None
