/** Create or edit a client: name, notes and aliases (one per line). */
import { useEffect, useRef, useState, type FormEvent } from 'react';

import { toApiError } from '../../api/client';
import type { ClientOut } from '../../api/clients';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { Textarea } from '../../components/ui/Textarea';
import { useToast } from '../../components/ui/useToast';
import { strings } from '../../strings';
import { errorSentence } from '../shared/errors';
import { MAX_NAME_LENGTH, MAX_NOTES_LENGTH, parseAliases } from './clientForm';
import { useCreateClient, useUpdateClient } from './queries';


export interface ClientDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The client to edit; null creates one. */
  readonly client: ClientOut | null;
  readonly onSaved?: (client: ClientOut) => void;
}

function ClientForm({ client, onOpenChange, onSaved }: Omit<ClientDialogProps, 'open'>) {
  const { toast } = useToast();
  const create = useCreateClient();
  const update = useUpdateClient(client?.id ?? '');
  const [name, setName] = useState(client?.name ?? '');
  const [notes, setNotes] = useState(client?.notes ?? '');
  const [aliases, setAliases] = useState(client?.aliases.join('\n') ?? '');
  const [nameError, setNameError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const busy = create.isPending || update.isPending;

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError(strings.clients.form.nameRequired);
      return;
    }
    if (trimmed.length > MAX_NAME_LENGTH) {
      setNameError(strings.clients.form.nameTooLong);
      return;
    }
    setNameError(null);
    setFormError(null);
    try {
      const body = { name: trimmed, notes, aliases: parseAliases(aliases) };
      const saved = client ? await update.mutateAsync(body) : await create.mutateAsync(body);
      toast({ tone: 'success', title: client ? strings.clients.form.saved : strings.clients.form.created, description: saved.name });
      onSaved?.(saved);
      onOpenChange(false);
    } catch (caught) {
      const error = toApiError(caught);
      if (error.status === 409) {
        setNameError(strings.clients.form.nameTaken);
      } else if (error.fieldMessage('name')) {
        setNameError(error.fieldMessage('name') ?? null);
      } else {
        setFormError(errorSentence(error));
      }
    }
  };

  return (
    <form id="client-form" className="co-form" onSubmit={(event) => void onSubmit(event)} noValidate>
      {formError && <Alert tone="danger">{formError}</Alert>}
      <Input
        ref={nameRef}
        label={strings.clients.form.name}
        value={name}
        maxLength={MAX_NAME_LENGTH}
        required
        disabled={busy}
        hint={strings.clients.form.nameHint}
        error={nameError}
        onChange={(event) => setName(event.target.value)}
      />
      <Textarea
        label={strings.clients.form.notes}
        optionalLabel={strings.common.optional}
        value={notes}
        maxLength={MAX_NOTES_LENGTH}
        disabled={busy}
        hint={strings.clients.form.notesHint}
        onChange={(event) => setNotes(event.target.value)}
      />
      <Textarea
        label={strings.clients.form.aliases}
        optionalLabel={strings.common.optional}
        value={aliases}
        rows={3}
        disabled={busy}
        hint={strings.clients.form.aliasesHint}
        onChange={(event) => setAliases(event.target.value)}
      />
      <div className="co-dialog__actions">
        <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
          {strings.common.cancel}
        </Button>
        <Button type="submit" variant="primary" loading={busy} loadingLabel={client ? strings.common.saving : strings.common.creating}>
          {client ? strings.common.save : strings.common.create}
        </Button>
      </div>
    </form>
  );
}

export function ClientDialog({ open, onOpenChange, client, onSaved }: ClientDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={client ? strings.clients.form.editTitle : strings.clients.form.createTitle}
      description={client ? strings.clients.form.editLead : strings.clients.form.createLead}
    >
      {open && <ClientForm client={client} onOpenChange={onOpenChange} onSaved={onSaved} />}
    </Dialog>
  );
}
