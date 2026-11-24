"""The external heartbeat watcher (phase C10): the dead-man URL.

EXTERNAL_HEARTBEAT_URL is a deployment secret (a dead-man URL usually
carries its own token in its query), empty by default: an empty URL keeps
the watcher off. While the worker ticks, every tick GETs the URL once
through the SSRF guard (app/security/ssrf.py, the same rules as the webhook
kinds) with the shared request machinery of app/notify/webhook.py: the
connection goes to a checked address, TLS still names and verifies the host,
no redirect is followed, 10 seconds in all.

The dead-man service alerts when the pings stop, so a failed GET is only
logged (one readable sentence that names no secret and no part of the URL
after the host); it never stops the tick or the pings that follow. The URL
itself never reaches a log line (it is in known_secrets for the redaction,
and no log call here receives it).
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from app.ext.notifications import DeliveryError
from app.notify.webhook import deliver
from app.security.ssrf import TargetRefused, check_target

if TYPE_CHECKING:
    from app.worker.loop import WorkerContext

logger = logging.getLogger(__name__)


async def external_heartbeat(context: "WorkerContext", now: datetime) -> None:
    """The tick hook (app/worker/loop.py TICK_HOOKS): GET the dead-man URL."""
    url = context.settings.external_heartbeat_url.get_secret_value()
    if not url:
        return
    try:
        target = await check_target(
            url,
            allow_private=context.settings.allow_private_targets,
            allowed_hosts=context.settings.allowed_hosts,
        )
    except TargetRefused as error:
        # The sentence names the host and the reason, never the path or the
        # query (they may hold the dead-man token).
        logger.warning("the outbound heartbeat was refused: %s", error)
        return
    try:
        await deliver(target, url, b"", method="GET")
    except DeliveryError as error:
        logger.warning("the outbound heartbeat failed: %s", error)
