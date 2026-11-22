/**
 * The morning digest of a day as it would be sent (digest/preview). The HTML
 * is shown in an iframe with an empty sandbox and srcdoc: no script, no
 * form, no navigation, no same-origin access, and the server's CSP applies
 * inside it too. The text version sits on a second tab as escaped text.
 */
import { useState } from 'react';

import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { ErrorState } from '../../components/ui/ErrorState';
import { Input } from '../../components/ui/Input';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { Tabs } from '../../components/ui/Tabs';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { useDigestPreview } from './queries';
import './dashboard.css';

export interface DigestPreviewDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

const HTML_TAB = 'html';
const TEXT_TAB = 'text';

export function DigestPreviewDialog({ open, onOpenChange }: DigestPreviewDialogProps) {
  const copy = strings.digest;
  // Null until the person picks a day: the first request sends no date, so
  // the server answers today in the digest zone, and the field shows the
  // date of that answer.
  const [picked, setPicked] = useState<string | null>(null);
  const [tab, setTab] = useState(HTML_TAB);
  const valid = picked === null || /^\d{4}-\d{2}-\d{2}$/.test(picked);
  const preview = useDigestPreview(valid ? picked : null, open && valid);
  const date = picked ?? preview.data?.date ?? '';

  let body: React.ReactNode;
  if (!valid) {
    body = <Alert tone="warning">{copy.invalidDate}</Alert>;
  } else if (preview.isPending) {
    body = (
      <SkeletonGroup label={copy.loading} className="co-digest__skeleton">
        <Skeleton height={20} width="60%" />
        <Skeleton height={320} radius="md" />
      </SkeletonGroup>
    );
  } else if (preview.isError) {
    body = <ErrorState error={preview.error} onRetry={() => void preview.refetch()} retrying={preview.isFetching} compact />;
  } else {
    const data = preview.data;
    body = (
      <div className="co-digest">
        <p className="co-digest__subject">
          <span className="co-digest__subject-label">{copy.subject}</span> <span className="co-digest__subject-text">{data.subject}</span>
        </p>
        <Tabs
          label={copy.title}
          value={tab}
          onValueChange={setTab}
          items={[
            {
              id: HTML_TAB,
              label: copy.html,
              content: data.html ? (
                <iframe className="co-digest__frame" title={copy.frameTitle} sandbox="" srcDoc={data.html} referrerPolicy="no-referrer" data-testid="digest-frame" />
              ) : (
                <p className="co-summary__muted">{copy.empty}</p>
              ),
            },
            {
              id: TEXT_TAB,
              label: copy.text,
              content: data.text ? (
                <div className="co-raw" tabIndex={0}>
                  <pre className="co-raw__pre" data-testid="digest-text">
                    {data.text}
                  </pre>
                </div>
              ) : (
                <p className="co-summary__muted">{copy.empty}</p>
              ),
            },
          ]}
        />
      </div>
    );
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={copy.title}
      description={fill(copy.lead, { date: valid && date ? date : '…' })}
      size="lg"
      footer={
        <Button variant="primary" onClick={() => onOpenChange(false)}>
          {strings.common.close}
        </Button>
      }
    >
      <div className="co-digest__controls">
        <Input label={copy.date} type="date" value={date} min="2000-01-01" max="2099-12-31" onChange={(event) => setPicked(event.target.value)} className="co-digest__date" />
      </div>
      {body}
    </Dialog>
  );
}
