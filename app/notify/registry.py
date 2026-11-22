"""The channel kinds the server can deliver with (the ChannelKind seam).

CE registers email (app/notify/email.py) and, from phase C9-I, slack, teams
and webhook (app/notify/webhook.py), all of app/db/models.py CHANNEL_KINDS
and the allowed values of the channels API, without a schema change. A
channel whose kind is not registered (a plugin kind of a later edition) can
be listed and deleted, but not created, changed, tested or sent to.
"""

from collections.abc import Iterable, Iterator, Mapping

from app.db.models import CHANNEL_KINDS
from app.ext.notifications import ChannelKind
from app.notify.email import EmailKind
from app.notify.webhook import SlackKind, TeamsKind, WebhookKind


class KindRegistry(Mapping[str, ChannelKind]):
    """The registered kinds by name; only names of CHANNEL_KINDS."""

    def __init__(self, kinds: Iterable[ChannelKind] = ()) -> None:
        self._kinds: dict[str, ChannelKind] = {}
        for kind in kinds:
            self.register(kind)

    def register(self, kind: ChannelKind) -> None:
        if kind.name not in CHANNEL_KINDS:
            raise ValueError(f"unknown channel kind {kind.name!r}")
        self._kinds[kind.name] = kind

    def __getitem__(self, name: str) -> ChannelKind:
        return self._kinds[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._kinds)

    def __len__(self) -> int:
        return len(self._kinds)


def default_kinds() -> KindRegistry:
    """The CE kinds: email, slack, teams and webhook (phase C9-I)."""
    return KindRegistry([EmailKind(), SlackKind(), TeamsKind(), WebhookKind()])
