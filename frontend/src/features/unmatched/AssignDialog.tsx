/**
 * Assign an unmatched result to an existing job: search the jobs, pick one,
 * and, when that job already has a match key that names another job name
 * than the mail, choose to keep it or replace it (replace_match_key). The
 * answer is read back in plain words (BindingSummary). A job that kept its
 * key can still get the mail's job name afterwards through the jobs route,
 * because a second assign of a bound result answers 409.
 */
import { Search } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { ApiError, toApiError } from '../../api/client';
import type { JobOut } from '../../api/jobs';
import type { Binding, UnmatchedOut } from '../../api/unmatched';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { useToast } from '../../components/ui/useToast';
import { fill } from '../../lib/format';
import { useDebouncedValue } from '../../lib/useDebouncedValue';
import { strings } from '../../strings';
import { errorSentence } from '../shared/errors';
import { BindingSummary } from './BindingSummary';
import { keyDiffers } from './names';
import { useAssignResult, useJobSearch, useReplaceMatchKey } from './queries';
import '../features.css';

export interface AssignDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly result: UnmatchedOut | null;
  /** Called once the result is bound (the queue no longer lists it). */
  readonly onBound?: (binding: Binding, job: JobOut) => void;
}

type KeyChoice = 'keep' | 'replace';

export function AssignDialog({ open, onOpenChange, result, onBound }: AssignDialogProps) {
  const copy = strings.unmatched;
  const { toast } = useToast();
  const assign = useAssignResult();
  const replaceKey = useReplaceMatchKey();
  const [search, setSearch] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [choice, setChoice] = useState<KeyChoice>('keep');
  const [jobError, setJobError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState<{ readonly binding: Binding; readonly job: JobOut; readonly replacedOldKey: string | null } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const q = useDebouncedValue(search.trim(), 250);
  const jobs = useJobSearch(q, open);

  // A fresh dialog for every open.
  useEffect(() => {
    if (open) {
      setSearch('');
      setJobId(null);
      setChoice('keep');
      setJobError(null);
      setFormError(null);
      setDone(null);
    }
  }, [open, result?.result_id]);

  const items = useMemo(() => jobs.data?.items ?? [], [jobs.data]);
  const job = items.find((item) => item.id === jobId) ?? done?.job ?? null;
  const differs = job !== null && result !== null && keyDiffers(job.match_key, result.job_name);
  const busy = assign.isPending;

  const submit = async () => {
    if (!result) {
      return;
    }
    if (!job) {
      setJobError(copy.assignChoose);
      return;
    }
    setJobError(null);
    setFormError(null);
    try {
      const binding = await assign.mutateAsync({ resultId: result.result_id, body: { job_id: job.id, replace_match_key: differs && choice === 'replace' } });
      toast({ tone: 'success', title: copy.assigned, description: job.name });
      setDone({ binding, job, replacedOldKey: null });
      onBound?.(binding, job);
    } catch (caught) {
      const error = toApiError(caught);
      setFormError(error instanceof ApiError && error.status === 409 ? copy.alreadyBound : errorSentence(error));
    }
  };

  const replaceNow = async () => {
    if (!done || !result?.job_name) {
      return;
    }
    const oldKey = done.binding.current_match_key;
    try {
      await replaceKey.mutateAsync({ jobId: done.job.id, matchKey: result.job_name });
      toast({ tone: 'success', title: copy.keyReplacedToast, description: done.job.name });
      setDone({ ...done, replacedOldKey: oldKey });
    } catch (caught) {
      setFormError(errorSentence(caught));
    }
  };

  const close = (next: boolean) => {
    if (!busy && !replaceKey.isPending) {
      onOpenChange(next);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title={copy.assignTitle}
      description={copy.assignLead}
      size="lg"
      initialFocusRef={searchRef}
      footer={
        done ? (
          <Button variant="primary" onClick={() => close(false)}>
            {copy.done}
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={() => close(false)} disabled={busy}>
              {strings.common.cancel}
            </Button>
            <Button variant="primary" onClick={() => void submit()} loading={busy} loadingLabel={copy.assigning}>
              {copy.assignSubmit}
            </Button>
          </>
        )
      }
    >
      <div className="co-form">
        {formError && <Alert tone="danger">{formError}</Alert>}
        {done && result ? (
          <BindingSummary
            binding={done.binding}
            jobName={done.job.name}
            clientName={done.job.client_name}
            resultJobName={result.job_name}
            resultClientHint={result.client_hint}
            onReplaceKey={!done.binding.match_key_set && done.replacedOldKey === null && keyDiffers(done.binding.current_match_key, result.job_name) ? () => void replaceNow() : undefined}
            replacing={replaceKey.isPending}
            replacedOldKey={done.replacedOldKey}
          />
        ) : (
          <>
            <Input
              ref={searchRef}
              label={copy.assignSearch}
              type="search"
              placeholder={copy.assignSearchPlaceholder}
              value={search}
              autoComplete="off"
              disabled={busy}
              trailing={<Search size={16} aria-hidden="true" className="co-assign__search-icon" />}
              onChange={(event) => setSearch(event.target.value)}
            />
            <div className="co-field">
              <span className="co-field__label" id="assign-jobs-label">
                {copy.assignJobs}
              </span>
              {jobs.isPending ? (
                <SkeletonGroup className="co-assign__list" label={copy.assignLoading}>
                  <Skeleton height={44} radius="md" />
                  <Skeleton height={44} radius="md" />
                  <Skeleton height={44} radius="md" />
                </SkeletonGroup>
              ) : jobs.isError ? (
                <Alert tone="danger">{errorSentence(jobs.error)}</Alert>
              ) : items.length === 0 ? (
                <p className="co-assign__empty">{copy.assignNoJobs}</p>
              ) : (
                <div className="co-assign__list" role="radiogroup" aria-labelledby="assign-jobs-label">
                  {items.map((item) => {
                    const selected = item.id === jobId;
                    return (
                      <div key={item.id}>
                        <button
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          className={selected ? 'co-assign__job co-assign__job--selected' : 'co-assign__job'}
                          disabled={busy}
                          onClick={() => {
                            setJobId(item.id);
                            setJobError(null);
                            setChoice('keep');
                          }}
                        >
                          <span className="co-assign__job-name">{item.name}</span>
                          <span className="co-assign__job-client">{item.client_name}</span>
                          {item.match_key && <span className="co-chip co-assign__job-key mono">{item.match_key}</span>}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
              {jobError && (
                <p className="co-field__error" role="alert">
                  {jobError}
                </p>
              )}
            </div>
            {differs && job && result && (
              <div className="co-keychoice" role="radiogroup" aria-labelledby="assign-key-label">
                <p className="co-keychoice__lead" id="assign-key-label">
                  {fill(copy.assignKeyKept, { key: job.match_key ?? '', name: result.job_name ?? '' })}
                </p>
                {(['keep', 'replace'] as const).map((option) => (
                  <label key={option} className={choice === option ? 'co-keychoice__option co-keychoice__option--selected' : 'co-keychoice__option'}>
                    <input type="radio" name="assign-key" className="co-keychoice__input" value={option} checked={choice === option} disabled={busy} onChange={() => setChoice(option)} />
                    <span className="co-keychoice__text">
                      <span className="co-keychoice__label">{option === 'keep' ? copy.keepKey : fill(copy.replaceKey, { name: result.job_name ?? '' })}</span>
                      <span className="co-keychoice__hint">{option === 'keep' ? copy.keepKeyLead : copy.replaceKeyLead}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
