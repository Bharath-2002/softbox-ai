"""Email at the route boundary.

Same pattern as ``get_token_issuer``: reads the instance ``bootstrap``
attached to ``app.state``, never constructs one — that would mean importing
``infrastructure``, which this layer may not do. No route uses this yet
(see CHECKLIST.md).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.ports.email_sender import EmailSender


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
