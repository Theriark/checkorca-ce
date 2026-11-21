/**
 * Import a Pack YAML file (POST packs/import). A file over the loader's
 * 64 KiB is refused before it is sent; a 422 lists the pack's issues by
 * path; a 409 says the id is built in. On success the pack opens.
 */
import { useEffect, useState } from 'react';

import { ApiError, toApiError } from '../../api/client';
import { MAX_PACK_BYTES, type PackDetail } from '../../api/packs';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { FileField } from '../../components/ui/FileField';
import { useToast } from '../../components/ui/useToast';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { errorSentence } from '../shared/errors';
import { describePointer } from './packIssues';
import { useImportPack } from './queries';
import '../features.css';

export interface ImportPackDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onImported?: (pack: PackDetail) => void;
}

export function ImportPackDialog({ open, onOpenChange, onImported }: ImportPackDialogProps) {
  const copy = strings.parsers;
  const { toast } = useToast();
  const importPack = useImportPack();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (open) {
      setFile(null);
      setFileError(null);
      setError(null);
    }
  }, [open]);

  const busy = importPack.isPending;
  const onFile = (next: File | null) => {
    setFile(next);
    setError(null);
    setFileError(next && next.size > MAX_PACK_BYTES ? fill(copy.importTooLarge, { size: (next.size / 1024).toFixed(1) }) : null);
  };

  const submit = async () => {
    if (!file) {
      setFileError(copy.importFileRequired);
      return;
    }
    if (file.size > MAX_PACK_BYTES) {
      return;
    }
    setError(null);
    try {
      const pack = await importPack.mutateAsync(file);
      toast({ tone: 'success', title: copy.imported, description: pack.id });
      onImported?.(pack);
      onOpenChange(false);
    } catch (caught) {
      setError(toApiError(caught));
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) {
          onOpenChange(next);
        }
      }}
      title={copy.importTitle}
      description={copy.importLead}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {strings.common.cancel}
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={busy} loadingLabel={copy.importing}>
            {copy.importSubmit}
          </Button>
        </>
      }
    >
      <div className="co-form">
        {error && (
          <Alert tone="danger" title={copy.importFailed}>
            {error.status === 409 ? copy.detail.builtinConflict : errorSentence(error)}
            {error.issues.length > 0 && (
              <ul className="co-issues co-issues--plain" aria-label={copy.importIssues}>
                {error.issues.map((issue, index) => (
                  <li key={`${issue.path}-${index}`}>
                    <span className="mono">{issue.path ? describePointer(issue.path) : copy.detail.issueWhole}</span>: {issue.message}
                  </li>
                ))}
              </ul>
            )}
          </Alert>
        )}
        <FileField label={copy.importFile} file={file} onFileChange={onFile} accept=".yaml,.yml,application/yaml,text/yaml" hint={copy.importFileHint} error={fileError} disabled={busy} />
      </div>
    </Dialog>
  );
}
