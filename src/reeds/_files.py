from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

__all__ = ["FileResponse"]


@dataclass(frozen=True)
class FileResponse:
    """A downloaded file: a delivery label or an invoice PDF."""

    data: bytes
    """The file's bytes."""
    content_type: str
    """``application/pdf`` for labels and invoices."""
    filename: str | None
    """The filename Reeds suggests (``Content-Disposition``), when it sends one."""

    def write_to(self, path: str | os.PathLike[str]) -> Path:
        """Saves the file and returns its path. A directory gets the suggested filename (or ``download.pdf``)."""
        target = Path(path)
        if target.is_dir():
            # Only the name: a suggested filename never picks the directory.
            name = Path(self.filename).name if self.filename else ""
            target = target / (name if name not in ("", ".", "..") else "download.pdf")
        target.write_bytes(self.data)
        return target


_ENCODED = re.compile(r"filename\*=UTF-8''([^;]+)", re.IGNORECASE)
_PLAIN = re.compile(r'filename="?([^";]+)"?', re.IGNORECASE)


def filename_of(disposition: str | None) -> str | None:
    if not disposition:
        return None
    encoded = _ENCODED.search(disposition)
    if encoded:
        return unquote(encoded.group(1).strip())
    plain = _PLAIN.search(disposition)
    return plain.group(1).strip() if plain else None
