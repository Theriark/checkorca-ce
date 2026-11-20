/** The inbox kinds: label and icon per kind (KindBadge.tsx shows both). */
import { FileUp, Inbox, MailSearch, Webhook, type LucideIcon } from 'lucide-react';

import type { InboxKind } from '../../api/inboxes';
import { strings } from '../../strings';

export const KIND_ICONS: Record<InboxKind, LucideIcon> = {
  smtp: Inbox,
  imap: MailSearch,
  webhook: Webhook,
  upload: FileUp,
};

export function kindLabel(kind: InboxKind): string {
  return strings.inboxes.kinds[kind];
}
