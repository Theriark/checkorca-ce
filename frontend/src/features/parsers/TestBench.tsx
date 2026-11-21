/**
 * The test bench: paste or upload a mail, run packs/test and read what the
 * packs made of it: the claiming pack, every pack's score, the packs skipped
 * (invalid, timeout, deadline, memory, with the path), the outcome and the
 * results with their spans highlighted in the mail as the engine read it.
 * With `pack` the YAML being edited takes the place of the stored pack with
 * its id. A 503 (two tests already run, or the child did not answer) waits a
 * few seconds and tries once more, then offers a button; never an error page.
 */
import { FlaskConical, Play } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ApiError, toApiError } from '../../api/client';
import { MAX_TEST_MAIL_BYTES, type BenchResult, type PackTestAnswer } from '../../api/packs';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { FileField } from '../../components/ui/FileField';
import { Textarea } from '../../components/ui/Textarea';
import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { ResultStatusBadge } from '../messages/MessageBadges';
import { errorSentence } from '../shared/errors';
import { HighlightedText, type TextSpan } from './HighlightedText';
import { BUSY_RETRY_SECONDS, SAMPLE_MAIL } from './benchSample';
import { describePointer } from './packIssues';
import { useBenchRun } from './queries';
import '../features.css';

export interface TestBenchProps {
  /** The Pack YAML being edited, in place of the stored pack with its id. */
  readonly pack?: string | null;
  /** Said above the form when a pack is being edited. */
  readonly editing?: boolean;
  readonly idPrefix?: string;
}

type BusyState = { readonly seconds: number; readonly retried: boolean } | null;

function spansOf(answer: PackTestAnswer, source: string): readonly TextSpan[] {
  return answer.results.flatMap((result, index) => result.spans.filter((span) => span.source === source).map((span) => ({ start: span.start, end: span.end, field: span.field, result: index + 1 })));
}

function ResultCard({ result, index }: { readonly result: BenchResult; readonly index: number }) {
  const copy = strings.bench;
  const field = strings.unmatched.field;
  const details = Object.entries(result.details);
  return (
    <li className="co-benchresult">
      <div className="co-benchresult__head">
        <span className="co-benchresult__title">{fill(copy.result, { index })}</span>
        <ResultStatusBadge status={result.status} size="sm" />
      </div>
      <dl className="co-kv co-kv--bench">
        <div className="co-kv__item">
          <dt className="co-kv__label">{field.job_name}</dt>
          <dd className="co-kv__value">{result.job_name ?? <span className="co-summary__muted">{strings.common.none}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{field.client_hint}</dt>
          <dd className="co-kv__value">{result.client_hint ?? <span className="co-summary__muted">{strings.common.none}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{field.started_at}</dt>
          <dd className="co-kv__value tabular">{result.started_at ? formatDateTime(result.started_at) : <span className="co-summary__muted">{strings.common.none}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{field.finished_at}</dt>
          <dd className="co-kv__value tabular">{result.finished_at ? formatDateTime(result.finished_at) : <span className="co-summary__muted">{strings.common.none}</span>}</dd>
        </div>
        <div className="co-kv__item">
          <dt className="co-kv__label">{field.run_id}</dt>
          <dd className="co-kv__value mono">{result.run_id ?? <span className="co-summary__muted">{strings.common.none}</span>}</dd>
        </div>
        <div className="co-kv__item co-kv__item--wide">
          <dt className="co-kv__label">{field.details}</dt>
          <dd className="co-kv__value">
            {details.length === 0 ? (
              <span className="co-summary__muted">{strings.unmatched.noDetails}</span>
            ) : (
              <dl className="co-details">
                {details.map(([key, value]) => (
                  <div key={key} className="co-details__row">
                    <dt className="co-details__key mono">{key}</dt>
                    <dd className="co-details__value">{value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </dd>
        </div>
      </dl>
    </li>
  );
}

function Answer({ answer, editedId }: { readonly answer: PackTestAnswer; readonly editedId: string | null }) {
  const copy = strings.bench;
  const reason = answer.reason ? (copy.outcomeReason[answer.reason as keyof typeof copy.outcomeReason] ?? answer.reason) : null;
  const headers: readonly { readonly key: 'sender' | 'to' | 'subject'; readonly source: string }[] = [
    { key: 'sender', source: 'from' },
    { key: 'to', source: 'to' },
    { key: 'subject', source: 'subject' },
  ];
  return (
    <div className="co-bench__answer" role="region" aria-label={copy.resultTitle}>
      <div className="co-bench__verdict">
        <div className="co-bench__claim">
          <span className="co-kv__label">{copy.claimedBy}</span>
          {answer.claimed_by ? (
            <span className="co-bench__claimant mono">{answer.claimed_by}</span>
          ) : answer.candidates.length > 1 ? (
            <span className="co-bench__noclaim">{fill(copy.tie, { packs: answer.candidates.join(', ') })}</span>
          ) : (
            <span className="co-bench__noclaim">{copy.noClaim}</span>
          )}
        </div>
        <div className="co-bench__outcome">
          <span className={`co-badge co-badge--${answer.outcome === 'parsed' ? 'success' : answer.outcome === 'unmatched' ? 'info' : 'danger'}`} data-outcome={answer.outcome}>
            <span className="co-badge__label">{copy.outcome[answer.outcome]}</span>
          </span>
          {reason && (
            <span className="co-bench__reason">
              {reason}
              {answer.path && <span className="mono"> {fill(copy.at, { path: describePointer(answer.path) })}</span>}
            </span>
          )}
        </div>
      </div>

      <div className="co-bench__grid">
        <section className="co-bench__section" aria-labelledby="bench-scores-title">
          <h3 id="bench-scores-title" className="co-split__title">
            {copy.scores}
          </h3>
          <p className="co-split__lead">{copy.scoresLead}</p>
          <table className="co-import__table co-scores">
            <caption className="sr-only">{copy.scores}</caption>
            <thead>
              <tr>
                <th scope="col">{copy.pack}</th>
                <th scope="col" className="co-scores__num">
                  {copy.matched}
                </th>
              </tr>
            </thead>
            <tbody>
              {answer.scores.map((score) => (
                <tr key={score.pack_id} className={score.pack_id === answer.claimed_by ? 'co-scores__row--claim' : undefined}>
                  <td className="mono">
                    {score.pack_id}
                    {score.pack_id === editedId && <span className="co-chip co-chip--icon">{copy.edited}</span>}
                  </td>
                  <td className="tabular co-scores__num">{score.matched}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {answer.skipped.length > 0 && (
            <div className="co-bench__skipped">
              <h4 className="co-split__title">{copy.skipped}</h4>
              <p className="co-split__lead">{copy.skippedLead}</p>
              <ul className="co-issues co-issues--plain" aria-label={copy.skipped}>
                {answer.skipped.map((item) => (
                  <li key={item.pack_id}>
                    <span className="mono">{item.pack_id}</span>: {copy.skipReason[item.reason]}
                    {item.path && <span className="mono"> {fill(copy.at, { path: describePointer(item.path) })}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="co-bench__section" aria-labelledby="bench-results-title">
          <h3 id="bench-results-title" className="co-split__title">
            {copy.results}
          </h3>
          <p className="co-split__lead">{copy.resultsLead}</p>
          {answer.results.length === 0 ? (
            <p className="co-summary__muted">{copy.noResults}</p>
          ) : (
            <ul className="co-benchresults">
              {answer.results.map((result, index) => (
                <ResultCard key={index} result={result} index={index + 1} />
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="co-bench__section" aria-labelledby="bench-mail-title">
        <h3 id="bench-mail-title" className="co-split__title">
          {copy.mailAsRead}
        </h3>
        <p className="co-split__lead">{copy.mailAsReadLead}</p>
        <dl className="co-rawhead">
          {headers.map(({ key, source }) => (
            <div key={key} className="co-rawhead__row">
              <dt>{copy.header[key]}</dt>
              <dd>
                <HighlightedText text={answer.mail[key]} spans={spansOf(answer, source)} />
              </dd>
            </div>
          ))}
          <div className="co-rawhead__row">
            <dt>{copy.header.sent_at}</dt>
            <dd>{answer.mail.sent_at ? formatDateTime(answer.mail.sent_at) : <span className="co-summary__muted">{copy.noSentAt}</span>}</dd>
          </div>
        </dl>
        <div className="co-raw co-raw--bench" tabIndex={0}>
          <pre className="co-raw__pre">
            <HighlightedText text={answer.mail.body} spans={spansOf(answer, 'body')} testId="bench-body" />
          </pre>
        </div>
        <p className="co-bench__legend">
          <mark className="co-span co-span--legend" aria-hidden="true">
            abc
          </mark>{' '}
          {copy.legend}
        </p>
      </section>
    </div>
  );
}

export function TestBench({ pack = null, editing = false, idPrefix = 'bench' }: TestBenchProps) {
  const copy = strings.bench;
  const run = useBenchRun();
  const [raw, setRaw] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [rawError, setRawError] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<BusyState>(null);
  const [answer, setAnswer] = useState<PackTestAnswer | null>(null);
  const [reading, setReading] = useState(false);
  const timer = useRef<number | null>(null);
  const editedId = useMemo(() => {
    const match = pack ? /^id:[ \t]*['"]?([a-z0-9][a-z0-9._-]*)/m.exec(pack) : null;
    return match?.[1] ?? null;
  }, [pack]);

  const clearTimer = () => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  };
  useEffect(() => clearTimer, []);

  const execute = useCallback(
    async (retried: boolean) => {
      setError(null);
      setBusy(null);
      try {
        const result = await run.mutateAsync({ raw, pack: pack ?? undefined });
        setAnswer(result);
      } catch (caught) {
        const apiError = toApiError(caught);
        if (apiError.status === 503) {
          const seconds = apiError.retryAfterSeconds && apiError.retryAfterSeconds > 0 && apiError.retryAfterSeconds <= 30 ? apiError.retryAfterSeconds : BUSY_RETRY_SECONDS;
          setBusy({ seconds, retried });
          return;
        }
        setError(apiError);
      }
    },
    [pack, raw, run],
  );

  // The one automatic retry: count the seconds down, then run again.
  useEffect(() => {
    if (!busy || busy.retried) {
      return undefined;
    }
    if (busy.seconds <= 0) {
      void execute(true);
      return undefined;
    }
    timer.current = window.setTimeout(() => setBusy((current) => (current ? { ...current, seconds: current.seconds - 1 } : current)), 1000);
    return clearTimer;
  }, [busy, execute]);

  const submit = () => {
    const bytes = new TextEncoder().encode(raw).length;
    if (!raw.trim()) {
      setRawError(copy.mailRequired);
      return;
    }
    if (bytes > MAX_TEST_MAIL_BYTES) {
      setRawError(fill(copy.tooLarge, { size: Math.ceil(bytes / 1024) }));
      return;
    }
    setRawError(null);
    void execute(false);
  };

  const onFile = async (next: File | null) => {
    setFile(next);
    setFileError(null);
    if (!next) {
      return;
    }
    if (next.size > MAX_TEST_MAIL_BYTES) {
      setFileError(fill(copy.tooLarge, { size: Math.ceil(next.size / 1024) }));
      return;
    }
    setReading(true);
    try {
      setRaw(await next.text());
      setRawError(null);
    } catch {
      setFileError(copy.uploadFailed);
    } finally {
      setReading(false);
    }
  };

  const running = run.isPending;
  return (
    <div className="co-bench">
      <div className="co-bench__form">
        {editing && <Alert tone="info">{copy.leadEdited}</Alert>}
        <Textarea
          id={`${idPrefix}-mail`}
          label={copy.mail}
          mono
          rows={10}
          value={raw}
          placeholder={copy.mailPlaceholder}
          hint={copy.mailHint}
          error={rawError}
          disabled={running}
          spellCheck={false}
          onChange={(event) => {
            setRaw(event.target.value);
            setRawError(null);
          }}
        />
        <div className="co-bench__tools">
          <FileField label={copy.upload} file={file} onFileChange={(next) => void onFile(next)} accept=".eml,message/rfc822,text/plain" hint={reading ? copy.readingFile : copy.uploadHint} error={fileError} disabled={running} />
          <Button variant="ghost" size="sm" iconStart={<FlaskConical size={16} />} disabled={running} onClick={() => setRaw(SAMPLE_MAIL)} title={copy.sampleLead}>
            {copy.sample}
          </Button>
        </div>
        {error && (
          <Alert tone="danger">
            {errorSentence(error)}
            {error.issues.length > 0 && (
              <ul className="co-issues co-issues--plain" aria-label={strings.parsers.detail.issuesTitle}>
                {error.issues.map((issue, index) => (
                  <li key={`${issue.path}-${index}`}>
                    <span className="mono">{issue.path ? describePointer(issue.path) : strings.parsers.detail.issueWhole}</span>: {issue.message}
                  </li>
                ))}
              </ul>
            )}
          </Alert>
        )}
        {busy && (
          <Alert tone="warning" title={copy.busyTitle} role="status">
            {busy.retried ? copy.busyGaveUp : fill(copy.busyLead, { seconds: busy.seconds })}
            <span className="co-binding__action">
              <Button size="sm" variant="secondary" onClick={() => void execute(true)} loading={running}>
                {copy.busyRetry}
              </Button>
            </span>
          </Alert>
        )}
        <div>
          <Button variant="primary" iconStart={<Play size={16} />} onClick={submit} loading={running} loadingLabel={copy.running} disabled={reading || (busy !== null && !busy.retried)}>
            {copy.run}
          </Button>
        </div>
      </div>
      {answer ? <Answer answer={answer} editedId={editedId} /> : <p className="co-bench__empty">{copy.empty}</p>}
    </div>
  );
}
