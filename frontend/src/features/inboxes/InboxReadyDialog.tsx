/**
 * What a sender needs, shown right after an inbox is created or a webhook
 * token is rotated: the SMTP address, the ingest URL and, for a webhook
 * inbox, the token. The token is in this dialog only; the API never returns
 * it again (docs/ingest.md, Inboxes).
 */
import { KeyRound } from 'lucide-react';

import type { InboxKind } from '../../api/inboxes';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { CopyField } from '../../components/ui/CopyField';
import { Dialog } from '../../components/ui/Dialog';
import { strings } from '../../strings';
import { KindBadge } from './KindBadge';
import '../features.css';

export interface InboxReveal {
  readonly kind: InboxKind;
  readonly label: string;
  readonly address: string | null;
  readonly ingestUrl: string | null;
  /** The webhook token, when it was just made. */
  readonly token: string | null;
  /** 'created' or 'rotated' changes the title and lead. */
  readonly reason: 'created' | 'rotated';
}

export interface InboxReadyDialogProps {
  readonly reveal: InboxReveal | null;
  readonly onClose: () => void;
}

export function InboxReadyDialog({ reveal, onClose }: InboxReadyDialogProps) {
  const open = reveal !== null;
  const rotated = reveal?.reason === 'rotated';
  const title = rotated ? strings.inboxes.tokenTitle : strings.inboxes.readyTitle;
  // The "shown once" sentence is said once, in the alert next to the token;
  // the lead says something else (C4-F item 6).
  const lead = rotated ? strings.inboxes.tokenRotatedLead : reveal?.token ? strings.inboxes.readyLead : strings.inboxes.readyLeadNoToken;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
      title={title}
      description={lead}
      footer={
        <Button variant="primary" onClick={onClose}>
          {strings.common.close}
        </Button>
      }
    >
      {reveal && (
        <div className="co-reveal">
          <div className="co-reveal__head">
            <KindBadge kind={reveal.kind} />
            <span className="co-reveal__label">{reveal.label}</span>
          </div>
          {reveal.kind === 'smtp' && <CopyField label={strings.inboxes.address} value={reveal.address} unavailable={strings.inboxes.noAddressFor} />}
          {!rotated && (reveal.kind === 'smtp' || reveal.kind === 'webhook') && (
            <CopyField label={strings.inboxes.ingestUrl} value={reveal.ingestUrl} unavailable={strings.inboxes.noUrlFor} />
          )}
          {reveal.token && (
            <>
              <Alert tone="warning" title={strings.inboxes.tokenShownOnce}>
                {strings.inboxes.tokenLead}
              </Alert>
              <CopyField label={strings.inboxes.token} value={reveal.token} unavailable={strings.inboxes.tokenNotSet} />
            </>
          )}
          {reveal.kind === 'imap' && (
            <p className="co-reveal__note">
              <KeyRound size={16} aria-hidden="true" />
              {strings.inboxForm.passwordHint}
            </p>
          )}
        </div>
      )}
    </Dialog>
  );
}
