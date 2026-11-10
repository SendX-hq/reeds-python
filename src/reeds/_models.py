from __future__ import annotations

from typing import Any

import pydantic

__all__ = ["ReedsModel"]


class ReedsModel(pydantic.BaseModel):
    """The base of every object the API returns.

    Fields Reeds adds later are kept (``extra="allow"``): read them with
    ``model.model_extra`` or ``to_dict()``.
    """

    model_config = pydantic.ConfigDict(extra="allow", populate_by_name=True, protected_namespaces=())

    def to_dict(self) -> dict[str, Any]:
        """The object as the API sent it: JSON field names, including fields this version doesn't know."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)
