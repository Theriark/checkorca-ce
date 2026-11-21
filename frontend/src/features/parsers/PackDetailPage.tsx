/**
 * /parsers/packs/:id: the pack's summary (vendor, version, source, status,
 * updated), the enabled switch, export, the YAML editor (CodeMirror 6;
 * read-only for a built-in pack, PUT for a custom one with the 422 issues
 * marked at their line) and the test bench, which runs the YAML in the
 * editor in place of the stored pack when it differs.
 */
import { Link, useParams } from '@tanstack/react-router';
import { ArrowLeft, Download, Puzzle, RotateCcw, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { ApiError, toApiError, type PackProblem } from '../../api/client';
import { MAX_PACK_BYTES, type PackDetail } from '../../api/packs';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { Switch } from '../../components/ui/Switch';
import { useToast } from '../../components/ui/useToast';
import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { PageHeader } from '../shared/PageHeader';
import { errorSentence } from '../shared/errors';
import { PackSourceChip, PackStatusBadge } from './PackBadges';
import { TestBench } from './TestBench';
import { exportPack } from './exportPack';
import { YamlEditor, type EditorMark } from './YamlEditor';
import { describePointer, locateIssue } from './packIssues';
import { usePack, useSavePack, useSetPackEnabled } from './queries';
import '../features.css';

function Crumbs() {
  return (
    <Link to="/parsers" className="co-pagehead__crumb">
      <ArrowLeft size={14} aria-hidden="true" />
      {strings.parsers.detail.back}
    </Link>
  );
}

interface LocatedIssue extends PackProblem {
  readonly line: number | null;
}

function Editor({ pack }: { readonly pack: PackDetail }) {
  const copy = strings.parsers.detail;
  const { toast } = useToast();
  const save = useSavePack();
  const [text, setText] = useState(pack.yaml);
  const [issues, setIssues] = useState<readonly PackProblem[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const readOnly = pack.source === 'builtin';

  // A pack reloaded from the server (after a save, or a reload) resets the
  // editor to what is stored.
  useEffect(() => {
    setText(pack.yaml);
    setIssues([]);
    setFormError(null);
  }, [pack.yaml]);

  const dirty = text !== pack.yaml;
  const bytes = useMemo(() => new TextEncoder().encode(text).length, [text]);
  const tooLarge = bytes > MAX_PACK_BYTES;
  const located = useMemo<readonly LocatedIssue[]>(() => issues.map((issue) => ({ ...issue, line: locateIssue(text, issue.path)?.line ?? null })), [issues, text]);
  const marks = useMemo<readonly EditorMark[]>(
    () =>
      issues.flatMap((issue) => {
        const where = locateIssue(text, issue.path);
        return where ? [{ from: where.from, to: where.to, message: issue.message }] : [{ from: 0, to: 0, message: issue.message }];
      }),
    [issues, text],
  );

  const onSave = async () => {
    if (readOnly || !dirty || tooLarge) {
      return;
    }
    setFormError(null);
    try {
      await save.mutateAsync({ packId: pack.id, yaml: text });
      setIssues([]);
      toast({ tone: 'success', title: copy.saved, description: pack.id });
    } catch (caught) {
      const error = toApiError(caught);
      if (error.issues.length > 0) {
        setIssues(error.issues);
        setFormError(null);
        return;
      }
      if (error instanceof ApiError && error.status === 409) {
        setFormError(error.title.toLowerCase().includes('built') ? copy.builtinConflict : copy.changedMeanwhile);
        return;
      }
      setFormError(errorSentence(error));
    }
  };

  const lines = text.split('\n').length;
  return (
    <section className="co-card" aria-labelledby="pack-editor-title">
      <div className="co-editor__head">
        <div className="co-card__head">
          <h2 id="pack-editor-title" className="co-card__title">
            {copy.editor}
          </h2>
          <p className="co-card__lead">{readOnly ? copy.editorLeadBuiltin : copy.editorLeadCustom}</p>
        </div>
        <div className="co-editor__meta">
          <span className="co-chip">{readOnly ? copy.readOnly : dirty ? copy.unsaved : fill(copy.lines, { count: lines })}</span>
          <span className={tooLarge ? 'co-chip co-chip--danger' : 'co-chip'}>{fill(copy.size, { size: (bytes / 1024).toFixed(1) })}</span>
        </div>
      </div>
      {formError && <Alert tone="danger">{formError}</Alert>}
      {tooLarge && <Alert tone="danger">{copy.tooLarge}</Alert>}
      {located.length > 0 && (
        <Alert tone="danger" title={copy.issuesTitle}>
          {copy.issuesLead}
          <ul className="co-issues" aria-label={copy.issuesTitle}>
            {located.map((issue, index) => (
              <li key={`${issue.path}-${index}`} className="co-issues__item">
                <span className="co-issues__where mono">
                  {issue.path ? fill(copy.issueAt, { path: describePointer(issue.path) }) : copy.issueWhole}
                  {issue.line !== null && <span className="co-issues__line"> · {fill(copy.line, { line: issue.line + 1 })}</span>}
                </span>
                <span className="co-issues__message">{issue.message}</span>
              </li>
            ))}
          </ul>
        </Alert>
      )}
      <YamlEditor value={text} onChange={setText} readOnly={readOnly} label={copy.editorLabel} marks={marks} />
      {!readOnly && (
        <div className="co-editor__actions">
          <Button variant="ghost" iconStart={<RotateCcw size={16} />} disabled={!dirty || save.isPending} onClick={() => setText(pack.yaml)}>
            {copy.discard}
          </Button>
          <Button variant="primary" iconStart={<Save size={16} />} disabled={!dirty || tooLarge} loading={save.isPending} loadingLabel={copy.saving} onClick={() => void onSave()}>
            {copy.save}
          </Button>
        </div>
      )}
      <div className="co-editor__bench">
        <div className="co-card__head">
          <h2 className="co-card__title">{strings.bench.title}</h2>
          <p className="co-card__lead">{strings.bench.lead}</p>
        </div>
        <TestBench pack={dirty ? text : null} editing={dirty} idPrefix={`bench-${pack.id}`} />
      </div>
    </section>
  );
}

export function PackDetailPage() {
  const { packId } = useParams({ strict: false }) as { readonly packId: string };
  const copy = strings.parsers;
  const { toast } = useToast();
  const query = usePack(packId);
  const setEnabled = useSetPackEnabled();

  if (query.isPending) {
    return (
      <div className="co-page">
        <PageHeader icon={Puzzle} title={<Skeleton width={280} height={28} />} crumbs={<Crumbs />} />
        <SkeletonGroup className="co-stack">
          <Skeleton height={120} radius="md" />
          <Skeleton height={420} radius="md" />
        </SkeletonGroup>
      </div>
    );
  }
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="co-page">
        <PageHeader icon={Puzzle} title={notFound ? copy.detail.notFoundTitle : copy.title} crumbs={<Crumbs />} />
        {notFound ? <ErrorState title={copy.detail.notFoundTitle} description={copy.detail.notFoundLead} /> : <ErrorState error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />}
      </div>
    );
  }
  const pack = query.data;
  const toggle = (enabled: boolean) => {
    void setEnabled
      .mutateAsync({ packId: pack.id, enabled })
      .then(() => toast({ tone: 'success', title: enabled ? copy.enabledToast : copy.disabledToast, description: copy.toggleLead }))
      .catch((error: unknown) => toast({ tone: 'danger', title: enabled ? copy.enabledToast : copy.disabledToast, description: errorSentence(error) }));
  };
  const onExport = () => {
    void exportPack(pack.id)
      .then(() => toast({ tone: 'success', title: copy.exported, description: `${pack.id}.yaml` }))
      .catch((error: unknown) => toast({ tone: 'danger', title: copy.exportFailed, description: errorSentence(error) }));
  };

  return (
    <div className="co-page">
      <PageHeader
        icon={Puzzle}
        title={<span className="mono">{pack.id}</span>}
        lead={pack.vendor}
        crumbs={<Crumbs />}
        badges={
          <>
            <PackSourceChip source={pack.source} />
            <PackStatusBadge status={pack.status} />
          </>
        }
        actions={
          <>
            <Switch label={copy.enabledLabel} checked={pack.enabled} onCheckedChange={toggle} disabled={setEnabled.isPending} />
            <Button variant="secondary" iconStart={<Download size={16} />} onClick={onExport}>
              {copy.export}
            </Button>
          </>
        }
      />
      <section className="co-card" aria-labelledby="pack-summary-title">
        <h2 id="pack-summary-title" className="co-card__title">
          {strings.clients.detail.summary}
        </h2>
        <dl className="co-kv">
          <div className="co-kv__item">
            <dt className="co-kv__label">{copy.detail.vendor}</dt>
            <dd className="co-kv__value">{pack.vendor}</dd>
          </div>
          <div className="co-kv__item">
            <dt className="co-kv__label">{copy.detail.version}</dt>
            <dd className="co-kv__value tabular">{pack.version}</dd>
          </div>
          <div className="co-kv__item">
            <dt className="co-kv__label">{copy.detail.source}</dt>
            <dd className="co-kv__value">{copy.source[pack.source]}</dd>
          </div>
          <div className="co-kv__item">
            <dt className="co-kv__label">{copy.columns.status}</dt>
            <dd className="co-kv__value">{copy.statusHint[pack.status]}</dd>
          </div>
          <div className="co-kv__item">
            <dt className="co-kv__label">{copy.detail.updated}</dt>
            <dd className="co-kv__value tabular">{formatDateTime(pack.updated_at)}</dd>
          </div>
        </dl>
      </section>
      <Editor pack={pack} />
    </div>
  );
}
