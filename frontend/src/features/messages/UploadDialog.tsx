/**
 * Upload an .eml file into an inbox (POST messages/upload, multipart, with
 * the CSRF token the client adds to every POST). A file over the API's 5 MiB
 * cap is refused before it is sent; the server's 413, 422 and 404 are shown
 * as one readable sentence. A duplicate is said so, with the stored message.
 * An answer that arrives after the dialog was closed or the page was left
 * changes nothing on screen (C4-F item 4).
 */
import { useEffect, useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import type { MessageAccepted } from '../../api/messages';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { FileField } from '../../components/ui/FileField';
import { Select } from '../../components/ui/Select';
import { useToast } from '../../components/ui/useToast';
import { strings } from '../../strings';
import { useInboxOptions } from '../inboxes/queries';
import { errorSentence } from '../shared/errors';
import { useUploadMessage } from './queries';
import { isTooLarge, tooLargeSentence } from './upload';
import '../features.css';

export interface UploadDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The inbox chosen in advance (from an inbox row). */
  readonly presetInboxId?: string | null;
  /** Called with the stored (or earlier, for a duplicate) message id. */
  readonly onStored?: (messageId: string, duplicate: boolean) => void;
}

export function UploadDialog({ open, onOpenChange, presetInboxId = null, onStored }: UploadDialogProps) {
  const { toast } = useToast();
  // The inboxes are asked for when the dialog opens, not while it is closed.
  const inboxes = useInboxOptions(open);
  const upload = useUploadMessage();
  const [inboxId, setInboxId] = useState<string>(presetInboxId ?? '');
  const [file, setFile] = useState<File | null>(null);
  const [inboxError, setInboxError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState<MessageAccepted | null>(null);
  // Which opening of the dialog a request belongs to: an answer for an
  // earlier opening, or one that lands after the dialog unmounted, is dropped.
  const opening = useRef(0);

  // A fresh dialog for every open.
  useEffect(() => {
    if (open) {
      opening.current += 1;
      setInboxId(presetInboxId ?? '');
      setFile(null);
      setInboxError(null);
      setFileError(null);
      setFormError(null);
      setDone(null);
    } else {
      opening.current += 1;
    }
  }, [open, presetInboxId]);
  useEffect(
    () => () => {
      opening.current = -1;
    },
    [],
  );

  const busy = upload.isPending;
  const options = (inboxes.data ?? []).map((inbox) => ({ value: inbox.id, label: `${inbox.label} (${strings.inboxes.kinds[inbox.kind]})` }));

  const close = (next: boolean) => {
    if (!busy) {
      onOpenChange(next);
    }
  };

  const onFile = (next: File | null) => {
    setFile(next);
    setFormError(null);
    setFileError(next && isTooLarge(next.size) ? tooLargeSentence(next.size) : null);
  };

  const submit = async () => {
    let valid = true;
    if (!inboxId) {
      setInboxError(strings.upload.inboxRequired);
      valid = false;
    } else {
      setInboxError(null);
    }
    if (!file) {
      setFileError(strings.upload.fileRequired);
      valid = false;
    } else if (isTooLarge(file.size)) {
      setFileError(tooLargeSentence(file.size));
      valid = false;
    } else {
      setFileError(null);
    }
    if (!valid || !file) {
      return;
    }
    setFormError(null);
    const started = opening.current;
    try {
      const result = await upload.mutateAsync({ file, inboxId });
      if (opening.current !== started) {
        return;
      }
      setDone(result);
      toast({ tone: result.duplicate ? 'info' : 'success', title: result.duplicate ? strings.upload.duplicate : strings.upload.done, description: file.name });
      if (!result.duplicate) {
        onStored?.(result.message_id, false);
        onOpenChange(false);
      }
    } catch (caught) {
      if (opening.current !== started) {
        return;
      }
      // An inbox deleted meanwhile answers 404: the choice is wrong, not the file.
      if (caught instanceof ApiError && caught.status === 404) {
        setInboxError(strings.upload.inboxGone);
        setFormError(errorSentence(caught));
        return;
      }
      setFormError(errorSentence(caught));
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title={strings.upload.title}
      description={strings.upload.lead}
      footer={
        done ? (
          <>
            <Button variant="ghost" onClick={() => close(false)}>
              {strings.common.close}
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                onStored?.(done.message_id, done.duplicate);
                onOpenChange(false);
              }}
            >
              {strings.upload.open}
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={() => close(false)} disabled={busy}>
              {strings.common.cancel}
            </Button>
            <Button variant="primary" onClick={() => void submit()} loading={busy} loadingLabel={strings.upload.uploading} disabled={inboxes.isPending}>
              {strings.upload.submit}
            </Button>
          </>
        )
      }
    >
      <div className="co-form">
        {formError && (
          <Alert tone="danger" title={strings.upload.failed}>
            {formError}
          </Alert>
        )}
        {done?.duplicate && (
          <Alert tone="info" title={strings.upload.duplicate}>
            {strings.upload.duplicateLead}
          </Alert>
        )}
        {!done && (
          <>
            <Select
              label={strings.upload.inbox}
              options={options}
              value={inboxId || undefined}
              onValueChange={(value) => {
                setInboxId(value);
                setInboxError(null);
              }}
              placeholder={inboxes.isPending ? strings.upload.loadingInboxes : options.length === 0 ? strings.upload.noInboxes : strings.upload.inboxPlaceholder}
              disabled={busy || inboxes.isPending || options.length === 0}
              error={inboxError ?? (inboxes.isError ? errorSentence(inboxes.error) : undefined)}
            />
            <FileField label={strings.upload.file} file={file} onFileChange={onFile} accept=".eml,message/rfc822" hint={strings.upload.fileHint} error={fileError} disabled={busy} />
          </>
        )}
      </div>
    </Dialog>
  );
}
