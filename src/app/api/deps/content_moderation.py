"""Content moderation at the route boundary. Same pattern as
``get_email_sender``/``get_object_storage``: reads the instance
``bootstrap`` attached to ``app.state``, never constructs one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.ports.content_moderation import ContentModerationScanner


def get_content_moderation_scanner(request: Request) -> ContentModerationScanner:
    scanner: ContentModerationScanner = request.app.state.content_moderation_scanner
    return scanner


ContentModerationScannerDep = Annotated[
    ContentModerationScanner, Depends(get_content_moderation_scanner)
]
