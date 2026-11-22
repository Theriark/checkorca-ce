"""Extension seams with their CE defaults (rnd-report-2 5.3).

Phase C1 adds AuditSink (audit.py); phase C4 adds MailboxConnector and
ResultSource (ingest.py); phase C5 adds ParserPackSource (parsers.py); phase
C7 adds SuppressionProvider (suppression.py) and EventSubscriber (events.py);
phase C8 adds ReportRenderer (reports.py); phase C9 adds ChannelKind and
EscalationPolicy (notifications.py); phase C12 freezes the full set at
EXTENSION_API_LEVEL 1.
"""

from typing import Final

# The level System status reports; phase C12 freezes the seams at this level.
EXTENSION_API_LEVEL: Final = 1
