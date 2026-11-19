import type { ReactNode } from 'react';

import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { strings } from '../../strings';

export interface ConfirmDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly title: ReactNode;
  readonly description: ReactNode;
  readonly confirmLabel: ReactNode;
  readonly loadingLabel?: ReactNode;
  readonly tone?: 'default' | 'danger';
  readonly busy?: boolean;
  /** An error from the last attempt, shown above the buttons. */
  readonly error?: string | null;
  readonly onConfirm: () => void;
  readonly children?: ReactNode;
}

/** One question, two buttons. The danger tone is for destructive confirms. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  loadingLabel,
  tone = 'default',
  busy = false,
  error,
  onConfirm,
  children,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) {
          onOpenChange(next);
        }
      }}
      title={title}
      description={description}
      size="sm"
      tone={tone}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {strings.common.cancel}
          </Button>
          <Button variant={tone === 'danger' ? 'danger' : 'primary'} onClick={onConfirm} loading={busy} loadingLabel={loadingLabel}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {error && <Alert tone="danger">{error}</Alert>}
      {children}
    </Dialog>
  );
}
