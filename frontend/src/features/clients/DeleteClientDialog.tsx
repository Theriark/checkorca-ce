/** The destructive confirm: the client's name typed again, sent as
 *  confirm_name; the server answers 409 when it does not match. */
import { useState } from 'react';

import { toApiError } from '../../api/client';
import type { ClientOut } from '../../api/clients';
import { Input } from '../../components/ui/Input';
import { useToast } from '../../components/ui/useToast';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { errorSentence } from '../shared/errors';
import { namesMatch } from './clientForm';
import { useDeleteClient } from './queries';

export interface DeleteClientDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly client: ClientOut;
  readonly onDeleted: () => void;
}

export function DeleteClientDialog({ open, onOpenChange, client, onDeleted }: DeleteClientDialogProps) {
  const { toast } = useToast();
  const remove = useDeleteClient(client.id);
  const [typed, setTyped] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const onConfirm = async () => {
    if (!namesMatch(typed, client.name)) {
      setFieldError(strings.clients.detail.deleteMismatch);
      return;
    }
    setFieldError(null);
    setError(null);
    try {
      await remove.mutateAsync(typed.trim());
      toast({ tone: 'success', title: strings.clients.detail.deleted, description: client.name });
      onOpenChange(false);
      onDeleted();
    } catch (caught) {
      const apiError = toApiError(caught);
      if (apiError.status === 409) {
        setFieldError(apiError.detail ?? strings.clients.detail.deleteMismatch);
      } else {
        setError(errorSentence(apiError));
      }
    }
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setTyped('');
          setError(null);
          setFieldError(null);
        }
        onOpenChange(next);
      }}
      tone="danger"
      title={fill(strings.clients.detail.deleteTitle, { name: client.name })}
      description={strings.clients.detail.deleteLead}
      confirmLabel={strings.common.delete}
      loadingLabel={strings.common.deleting}
      busy={remove.isPending}
      error={error}
      onConfirm={() => void onConfirm()}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onConfirm();
        }}
      >
        <Input
          label={strings.clients.detail.deleteConfirmLabel}
          placeholder={client.name}
          value={typed}
          autoComplete="off"
          spellCheck={false}
          error={fieldError}
          disabled={remove.isPending}
          onChange={(event) => setTyped(event.target.value)}
        />
      </form>
    </ConfirmDialog>
  );
}
