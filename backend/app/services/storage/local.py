import os
import shutil
from typing import BinaryIO

from app.services.parsing.service import extension_of


class LocalStorageBackend:
    """Stores files on local disk under ``upload_dir/<tenant_id>/<workbook_id>/original<ext>``.

    Paths are built entirely from server-generated ids and a validated
    extension -- the client-supplied filename is never used to build a path,
    only recorded as metadata (``original_filename`` on the Workbook row).
    """

    def __init__(self, upload_dir: str):
        self.upload_dir = upload_dir

    def save(self, tenant_id: str, workbook_id: str, filename: str, fileobj: BinaryIO) -> str:
        ext = extension_of(filename)
        directory = os.path.join(self.upload_dir, tenant_id, workbook_id)
        os.makedirs(directory, exist_ok=True)
        stored_path = os.path.join(directory, f"original{ext}")
        with open(stored_path, "wb") as out:
            shutil.copyfileobj(fileobj, out)
        return stored_path

    def path_for(self, stored_path: str) -> str:
        return stored_path
