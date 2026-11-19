/**
 * The schedule editor of the job drawer: kind (daily, cron, interval), the
 * expression (a list of times for daily), the IANA zone, and the live preview
 * of the next five times with the server's own error text.
 */
import { Loader2, Plus, X } from 'lucide-react';
import { useId, useMemo } from 'react';

import { SCHEDULE_KINDS, type ScheduleKind } from '../../api/jobs';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { fill, formatDateTime, formatUtcTime } from '../../lib/format';
import { knownTimeZones } from '../../lib/timezones';
import { strings } from '../../strings';
import { scheduleKindLabel } from './jobState';
import { scheduleExpression, type ScheduleValue } from './scheduleValue';
import { useSchedulePreview, type PreviewState } from './useSchedulePreview';
import '../features.css';

export interface ScheduleEditorProps {
  readonly value: ScheduleValue;
  readonly onChange: (value: ScheduleValue) => void;
  readonly anchor?: string | null;
  readonly disabled?: boolean;
  /** Server-side field errors (from a failed save). */
  readonly errors?: { readonly expr?: string; readonly timezone?: string };
}

export function ScheduleEditor({ value, onChange, anchor, disabled, errors }: ScheduleEditorProps) {
  const listId = useId();
  const kindGroupId = useId();
  const zones = useMemo(() => knownTimeZones(), []);
  const expression = scheduleExpression(value);
  const preview = useSchedulePreview({ kind: value.kind, expr: expression, timezone: value.timezone, anchor });
  const previewExprError = preview.status === 'invalid' && preview.field !== 'timezone' ? preview.message : undefined;
  const previewZoneError = preview.status === 'invalid' && preview.field === 'timezone' ? preview.message : undefined;

  const setKind = (kind: ScheduleKind) => onChange({ ...value, kind });
  const setTime = (index: number, time: string) =>
    onChange({ ...value, times: value.times.map((item, at) => (at === index ? time : item)) });
  const addTime = () => onChange({ ...value, times: [...value.times, ''] });
  const removeTime = (index: number) => {
    const times = value.times.filter((_, at) => at !== index);
    onChange({ ...value, times: times.length > 0 ? times : [''] });
  };

  return (
    <div className="co-form__section">
      <div className="co-form__section-title">{strings.jobForm.sectionSchedule}</div>
      <div className="co-schedule">
      <div className="co-schedule__fields">
      <div className="co-field">
        <span className="co-field__label" id={kindGroupId}>
          {strings.jobForm.scheduleKind}
        </span>
        <div className="co-segmented" role="group" aria-labelledby={kindGroupId}>
          {SCHEDULE_KINDS.map((kind) => (
            <button
              key={kind}
              type="button"
              className="co-segmented__option"
              aria-pressed={value.kind === kind}
              disabled={disabled}
              onClick={() => setKind(kind)}
            >
              {scheduleKindLabel(kind)}
            </button>
          ))}
        </div>
      </div>

      {value.kind === 'daily' ? (
        <div className="co-times">
          <span className="co-field__label">{strings.jobForm.dailyTimes}</span>
          <ul className="co-times__list">
            {value.times.map((time, index) => (
              <li key={index} className="co-times__row">
                <Input
                  label={<span className="sr-only">{fill(strings.jobForm.timeLabel, { index: index + 1 })}</span>}
                  type="time"
                  value={time}
                  step={60}
                  disabled={disabled}
                  required
                  onChange={(event) => setTime(index, event.target.value)}
                  error={index === 0 ? (errors?.expr ?? previewExprError) : undefined}
                />
                {value.times.length > 1 && (
                  <Button variant="ghost" iconOnly iconStart={<X size={16} />} disabled={disabled} onClick={() => removeTime(index)}>
                    {fill(strings.jobForm.removeTime, { time: time || String(index + 1) })}
                  </Button>
                )}
              </li>
            ))}
          </ul>
          <div>
            <Button size="sm" variant="secondary" iconStart={<Plus size={16} />} disabled={disabled} onClick={addTime}>
              {strings.jobForm.addTime}
            </Button>
          </div>
          <p className="co-field__hint">{strings.jobForm.dailyHint}</p>
        </div>
      ) : (
        <Input
          label={strings.jobForm.expression}
          mono
          value={value.expr}
          disabled={disabled}
          required
          autoComplete="off"
          spellCheck={false}
          placeholder={value.kind === 'cron' ? strings.jobForm.cronPlaceholder : strings.jobForm.intervalPlaceholder}
          hint={value.kind === 'cron' ? strings.jobForm.cronHint : strings.jobForm.intervalHint}
          error={errors?.expr ?? previewExprError}
          onChange={(event) => onChange({ ...value, expr: event.target.value })}
        />
      )}

      <Input
        label={strings.jobForm.timezone}
        value={value.timezone}
        disabled={disabled}
        required
        list={listId}
        autoComplete="off"
        spellCheck={false}
        hint={strings.jobForm.timezoneHint}
        error={errors?.timezone ?? previewZoneError}
        onChange={(event) => onChange({ ...value, timezone: event.target.value })}
      />
      <datalist id={listId}>
        {zones.map((zone) => (
          <option key={zone} value={zone} />
        ))}
      </datalist>
      </div>

      <SchedulePreviewPanel state={preview} timezone={value.timezone} interval={value.kind === 'interval'} />
      </div>
    </div>
  );
}

function PreviewList({ next, local, timezone }: { readonly next: readonly string[]; readonly local: readonly string[]; readonly timezone: string }) {
  return (
    <ol className="co-preview__list">
      {next.map((iso, index) => (
        <li key={iso} className="co-preview__item">
          <span className="co-preview__index tabular" aria-hidden="true">
            {index + 1}
          </span>
          <span className="co-preview__local tabular">{formatDateTime(local[index] ?? iso, timezone)}</span>
          <span className="co-preview__utc tabular">{formatUtcTime(iso)}</span>
        </li>
      ))}
    </ol>
  );
}

export function SchedulePreviewPanel({ state, timezone, interval }: { readonly state: PreviewState; readonly timezone: string; readonly interval: boolean }) {
  return (
    <section className="co-preview" aria-live="polite" aria-busy={state.status === 'checking'}>
      <div className="co-preview__head">
        <h3 className="co-preview__title">{strings.schedule.previewTitle}</h3>
        {state.status === 'checking' && (
          <span className="co-preview__status">
            <Loader2 size={14} aria-hidden="true" />
            {strings.schedule.checking}
          </span>
        )}
      </div>
      {state.status === 'idle' && <p className="co-preview__empty">{strings.schedule.idle}</p>}
      {state.status === 'checking' && state.previous && <PreviewList next={state.previous.next} local={state.previous.local} timezone={timezone} />}
      {state.status === 'checking' && !state.previous && <p className="co-preview__empty">{strings.schedule.checking}</p>}
      {state.status === 'ready' && <PreviewList next={state.preview.next} local={state.preview.local} timezone={timezone} />}
      {state.status === 'invalid' && (
        <Alert tone="warning" title={strings.schedule.invalidTitle} role="status">
          {state.message}
        </Alert>
      )}
      {state.status === 'failed' && (
        <Alert tone="danger" role="status">
          {state.message}
        </Alert>
      )}
      {interval && <p className="co-preview__note">{strings.schedule.intervalNote}</p>}
    </section>
  );
}
