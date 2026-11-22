"""One delivery through a channel kind, shared by the dispatcher and
channels/{id}/test: a time limit, and every failure as one stored sentence
that never holds the channel's secret."""

import asyncio
import logging
import traceback
from collections.abc import Mapping
from typing import Any, Final

from app.db.models import ERROR_LENGTH
from app.ext.notifications import ChannelKind, DeliveryError, Message, Outbound
from app.security.crypto import MASK
from app.settings import Settings

# Seconds one delivery may take in all.
SEND_TIMEOUT: Final = 90.0

logger = logging.getLogger(__name__)


def redact(text: str, secret: str | None) -> str:
    """The error as stored: never the secret, at most ERROR_LENGTH long."""
    if secret:
        text = text.replace(secret, MASK)
    return text[:ERROR_LENGTH]


def outbound_of(settings: Settings) -> Outbound:
    """The SSRF rules of ALLOW_PRIVATE_TARGETS and OUTBOUND_ALLOWED_HOSTS."""
    return Outbound(
        allow_private=settings.allow_private_targets,
        allowed_hosts=settings.allowed_hosts,
    )


async def send_message(
    kind: ChannelKind,
    config: Mapping[str, Any],
    secret: str | None,
    message: Message,
    outbound: Outbound,
) -> str | None:
    """Deliver the message; None when it was delivered, else why not."""
    try:
        async with asyncio.timeout(SEND_TIMEOUT):
            await kind.send(config, secret, message, outbound)
    except DeliveryError as error:
        return redact(error.detail, secret)
    except TimeoutError:
        return f"The delivery took longer than {SEND_TIMEOUT:.0f} seconds."
    except Exception as error:
        # The class and the stack only: the text may hold anything, and a
        # logged exception repeats it.
        logger.error(
            "channel kind %s failed (%s)\n%s",
            kind.name,
            type(error).__name__,
            "".join(traceback.format_tb(error.__traceback__)),
        )
        return f"The {kind.name} delivery failed ({type(error).__name__})."
    return None
