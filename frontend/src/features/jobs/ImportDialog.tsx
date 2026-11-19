/**
 * CSV import in two steps: a dry run that lists the row errors by row number
 * and the counts, then the import of the rows that passed. The file is sent
 * twice; a changed file has to be checked again.
 */
import { useRef, useState } from 'react';

import type { ImportResult } from '../../api/jobs';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { FileField } from '../../components/ui/FileField';
import { useToast } from '../../components/ui/useToast';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { errorSentence } from '../shared/errors';
import { useImportJobs } from './queries';
import '../features.css';

export interface ImportDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

function Counts({ result, checked }: { readonly result: ImportResult; readonly checked: boolean }) {
  const labels = checked
    ? [strings.importCsv.willCreate, strings.importCsv.willUpdate, strings.importCsv.clientsToCreate]
    : [strings.importCsv.created, strings.importCsv.updated, strings.importCsv.clientsCreated];
  const values = [result.created, result.updated, result.clients_created];
  return (
    <dl className="co-import__counts">
      {labels.map((label, index) => (
        <div key={label} className="co-import__count">
          <dd className="co-import__count-value tabular">{values[index]}</dd>
          <dt className="co-import__count-label">{label}</dt>
        </div>
      ))}
    </dl>
  );
}

export function ImportDialog({ open, onOpenChange }: ImportDialogProps) {
  const { toast } = useToast();
  const importJobs = useImportJobs();
  const [file, setFile] = useState<File | null>(null);
  const [checked, setChecked] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const checkedFile = useRef<File | null>(null);

  const reset = () => {
    setFile(null);
    setChecked(null);
    setDone(null);
    setFileError(null);
    setFieldError(null);
    checkedFile.current = null;
  };

  const close = (next: boolean) => {
    if (importJobs.isPending) {
      return;
    }
    if (!next) {
      reset();
    }
    onOpenChange(next);
  };

  const onFile = (next: File | null) => {
    setFile(next);
    setChecked(null);
    setDone(null);
    setFileError(null);
    setFieldError(null);
  };

  const check = async () => {
    if (!file) {
      setFieldError(strings.importCsv.fileRequired);
      return;
    }
    setFieldError(null);
    setFileError(null);
    try {
      const result = await importJobs.mutateAsync({ file, dryRun: true });
      checkedFile.current = file;
      setChecked(result);
    } catch (caught) {
      setFileError(errorSentence(caught));
    }
  };

  const run = async () => {
    if (!file || !checked) {
      return;
    }
    if (checkedFile.current !== file) {
      setChecked(null);
      setFieldError(strings.importCsv.fileChanged);
      return;
    }
    setFileError(null);
    try {
      const result = await importJobs.mutateAsync({ file, dryRun: false });
      setDone(result);
      toast({
        tone: 'success',
        title: strings.importCsv.done,
        description: fill(strings.importCsv.doneLead, { created: result.created, updated: result.updated, clients: result.clients_created }),
      });
    } catch (caught) {
      setFileError(errorSentence(caught));
    }
  };

  const importable = checked ? checked.created + checked.updated : 0;
  const busy = importJobs.isPending;
  const checking = busy && importJobs.variables?.dryRun === true;
  const importing = busy && importJobs.variables?.dryRun === false;

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title={strings.importCsv.title}
      description={strings.importCsv.lead}
      size="lg"
      footer={
        done ? (
          <Button variant="primary" onClick={() => close(false)}>
            {strings.common.close}
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={() => close(false)} disabled={busy}>
              {strings.common.cancel}
            </Button>
            {checked ? (
              <>
                <Button variant="secondary" onClick={() => void check()} disabled={busy}>
                  {strings.importCsv.recheck}
                </Button>
                <Button variant="primary" onClick={() => void run()} disabled={importable === 0 || busy} loading={importing} loadingLabel={strings.importCsv.importing}>
                  {fill(strings.importCsv.importCount, { count: importable })}
                </Button>
              </>
            ) : (
              <Button variant="primary" onClick={() => void check()} loading={checking} loadingLabel={strings.importCsv.checking} disabled={busy}>
                {strings.importCsv.check}
              </Button>
            )}
          </>
        )
      }
    >
      <div className="co-import">
        {!done && (
          <FileField
            label={strings.importCsv.file}
            file={file}
            onFileChange={onFile}
            accept=".csv,text/csv"
            hint={strings.importCsv.fileHint}
            error={fieldError}
            disabled={busy}
          />
        )}
        {fileError && (
          <Alert tone="danger" title={strings.importCsv.fileError}>
            {fileError}
          </Alert>
        )}
        {done && (
          <>
            <Alert tone="success" title={strings.importCsv.done}>
              {fill(strings.importCsv.doneLead, { created: done.created, updated: done.updated, clients: done.clients_created })}
            </Alert>
            <Counts result={done} checked={false} />
          </>
        )}
        {checked && !done && (
          <>
            <h3 className="co-card__title">{strings.importCsv.resultTitle}</h3>
            <Counts result={checked} checked />
            {checked.errors.length === 0 ? (
              <Alert tone="success">{strings.importCsv.allGood}</Alert>
            ) : (
              <Alert tone="warning" title={importable === 0 ? strings.importCsv.nothingToImport : fill(strings.importCsv.skippedNote, { count: checked.errors.length })}>
                {strings.importCsv.errorsLead}
              </Alert>
            )}
          </>
        )}
        {((checked && !done && checked.errors.length > 0) || (done && done.errors.length > 0)) && (
          <div className="co-import__errors">
            <table className="co-import__table">
              <caption className="sr-only">{strings.importCsv.rowsWithErrors}</caption>
              <thead>
                <tr>
                  <th scope="col">{strings.importCsv.row}</th>
                  <th scope="col">{strings.importCsv.problem}</th>
                </tr>
              </thead>
              <tbody>
                {(done ?? checked)?.errors.map((item) => (
                  <tr key={`${item.row}-${item.message}`}>
                    <td className="co-import__row tabular">{item.row}</td>
                    <td>{item.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Dialog>
  );
}
