from typing import BinaryIO, Protocol


class StorageBackend(Protocol):
    def save(self, tenant_id: str, workbook_id: str, filename: str, fileobj: BinaryIO) -> str:
        """Persist the file unmodified and return a backend-specific stored path."""
        ...

    def path_for(self, stored_path: str) -> str:
        """Resolve a stored path to a local filesystem path usable by the parsers."""
        ...
