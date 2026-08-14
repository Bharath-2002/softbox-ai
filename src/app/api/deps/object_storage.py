"""Object storage at the route boundary. Same pattern as
``get_email_sender``: reads the instance ``bootstrap`` attached to
``app.state``, never constructs one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.ports.object_storage import ObjectStorage


def get_object_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage = request.app.state.object_storage
    return storage


ObjectStorageDep = Annotated[ObjectStorage, Depends(get_object_storage)]
