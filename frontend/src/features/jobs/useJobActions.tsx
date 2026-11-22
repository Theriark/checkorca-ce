/**
 * Pause, resume, archive and restore a job, with their dialogs, shared by the
 * jobs page and the client page. The hook returns the actions and the dialogs
 * to render once.
 */
import { useCallback, useState, type ReactNode } from 'react';

import { toApiError } from '../../api/client';
import type { JobOut } from '../../api/jobs';
import { Input } from '../../components/ui/Input';
import { copyText } from '../../components/ui/copyText';
import { useToast } from '../../components/ui/useToast';
import { fill, localInputToIso, nowForLocalInput } from '../../lib/format';
import { strings } from '../../strings';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { errorSentence } from '../shared/errors';
import { useArchiveJob, usePauseJob, useRestoreJob, useResumeJob } from './queries';

/** What the pause, resume, archive and restore actions need of a job: the
 *  attention list of the morning check has these two fields, not a JobOut. */
export type JobRef = Pick<JobOut, 'id' | 'name'>;

export interface JobActions {
  readonly pause: (job: JobRef) => void;
  readonly resume: (job: JobRef) => void;
  readonly archive: (job: JobRef) => void;
  readonly restore: (job: JobRef) => void;
  readonly copyPing: (job: JobOut) => void;
  readonly dialogs: ReactNode;
}

export function useJobActions(): JobActions {
  const { toast } = useToast();
  const pauseMutation = usePauseJob();
  const resumeMutation = useResumeJob();
  const archiveMutation = useArchiveJob();
  const restoreMutation = useRestoreJob();
  const [pauseTarget, setPauseTarget] = useState<JobRef | null>(null);
  const [pauseUntil, setPauseUntil] = useState('');
  const [pauseError, setPauseError] = useState<string | null>(null);
  const [pauseFieldError, setPauseFieldError] = useState<string | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<JobRef | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const pause = useCallback((job: JobRef) => {
    setPauseUntil('');
    setPauseError(null);
    setPauseFieldError(null);
    setPauseTarget(job);
  }, []);

  const confirmPause = async () => {
    if (!pauseTarget) {
      return;
    }
    const until = localInputToIso(pauseUntil);
    if (pauseUntil && !until) {
      setPauseFieldError(strings.jobs.pauseUntilHint);
      return;
    }
    setPauseError(null);
    setPauseFieldError(null);
    try {
      await pauseMutation.mutateAsync({ jobId: pauseTarget.id, body: until ? { until } : undefined });
      toast({ tone: 'success', title: strings.jobs.paused, description: pauseTarget.name });
      setPauseTarget(null);
    } catch (caught) {
      const error = toApiError(caught);
      const field = error.fieldMessage('until');
      if (field) {
        setPauseFieldError(field);
      } else {
        setPauseError(errorSentence(error));
      }
    }
  };

  // mutateAsync per call: TanStack runs per-call mutate callbacks only for
  // the last call, so two quick resumes would lose a toast.
  const resume = useCallback(
    (job: JobRef) => {
      void resumeMutation
        .mutateAsync(job.id)
        .then(() => toast({ tone: 'success', title: strings.jobs.resumed, description: job.name }))
        .catch((error: unknown) => toast({ tone: 'danger', title: strings.jobs.resume, description: errorSentence(error) }));
    },
    [resumeMutation, toast],
  );

  const archive = useCallback((job: JobRef) => {
    setArchiveError(null);
    setArchiveTarget(job);
  }, []);

  const confirmArchive = async () => {
    if (!archiveTarget) {
      return;
    }
    try {
      await archiveMutation.mutateAsync(archiveTarget.id);
      toast({ tone: 'success', title: strings.jobs.archivedToast, description: archiveTarget.name });
      setArchiveTarget(null);
    } catch (caught) {
      setArchiveError(errorSentence(caught));
    }
  };

  const restore = useCallback(
    (job: JobRef) => {
      void restoreMutation
        .mutateAsync(job.id)
        .then(() => toast({ tone: 'success', title: strings.jobs.restoredToast, description: job.name }))
        .catch((error: unknown) => toast({ tone: 'danger', title: strings.jobs.restore, description: errorSentence(error) }));
    },
    [restoreMutation, toast],
  );

  const copyPing = useCallback(
    (job: JobOut) => {
      if (!job.ping_url) {
        toast({ tone: 'info', title: strings.jobForm.pingUnavailable });
        return;
      }
      void copyText(job.ping_url).then((ok) =>
        toast(ok ? { tone: 'success', title: strings.common.copied } : { tone: 'danger', title: strings.common.copyFailed }),
      );
    },
    [toast],
  );

  const dialogs = (
    <>
      <ConfirmDialog
        open={pauseTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPauseTarget(null);
          }
        }}
        title={fill(strings.jobs.pauseTitle, { name: pauseTarget?.name ?? '' })}
        description={strings.jobs.pauseLead}
        confirmLabel={strings.jobs.pause}
        busy={pauseMutation.isPending}
        error={pauseError}
        onConfirm={() => void confirmPause()}
      >
        <Input
          label={strings.jobs.pauseUntil}
          type="datetime-local"
          optionalLabel={strings.common.optional}
          min={nowForLocalInput()}
          value={pauseUntil}
          hint={strings.jobs.pauseUntilHint}
          error={pauseFieldError}
          disabled={pauseMutation.isPending}
          onChange={(event) => setPauseUntil(event.target.value)}
        />
      </ConfirmDialog>
      <ConfirmDialog
        open={archiveTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setArchiveTarget(null);
          }
        }}
        title={fill(strings.jobs.archiveTitle, { name: archiveTarget?.name ?? '' })}
        description={strings.jobs.archiveLead}
        confirmLabel={strings.jobs.archive}
        busy={archiveMutation.isPending}
        error={archiveError}
        onConfirm={() => void confirmArchive()}
      />
    </>
  );

  return { pause, resume, archive, restore, copyPing, dialogs };
}
