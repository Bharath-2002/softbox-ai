"""Channel publishing at the route boundary — the same shape
``api/deps/text_generation.py``/``api/deps/image_generation.py`` use: no
honest default adapter exists (no Pinterest/Instagram/Facebook credentials
anywhere in this repo), so ``bootstrap/app.py`` never sets
``app.state.channel_publisher``, and ``getattr`` with a ``None`` default
turns an unset provider into a documented 503 rather than a bare
``AttributeError`` surfacing as an unexplained 500.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.ports.channel_publisher import ChannelPublisher
from app.shared.errors import UnavailableError


def get_channel_publisher(request: Request) -> ChannelPublisher:
    publisher: ChannelPublisher | None = getattr(request.app.state, "channel_publisher", None)
    if publisher is None:
        raise UnavailableError(
            "Channel publishing is not configured on this deployment.",
            code="channel_publisher_unavailable",
        )
    return publisher


ChannelPublisherDep = Annotated[ChannelPublisher, Depends(get_channel_publisher)]
