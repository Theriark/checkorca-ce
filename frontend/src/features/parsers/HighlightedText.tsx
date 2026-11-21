/**
 * Text with the spans the engine read marked: the value of each field is a
 * <mark> with a label for assistive technology ("job_name of result 1"). The
 * text is rendered as text; nothing here is HTML.
 */
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { splitBySpans, type TextSpan } from './spans';
import '../features.css';

export type { TextSpan } from './spans';

export function HighlightedText({ text, spans, className, testId }: { readonly text: string; readonly spans: readonly TextSpan[]; readonly className?: string; readonly testId?: string }) {
  const pieces = splitBySpans(text, spans);
  return (
    <span className={className} data-testid={testId}>
      {pieces.map((piece, index) =>
        piece.span ? (
          <mark key={index} className="co-span" data-field={piece.span.field} title={fill(strings.bench.spanLabel, { field: piece.span.field, index: piece.span.result })}>
            <span className="sr-only">{fill(strings.bench.spanLabel, { field: piece.span.field, index: piece.span.result })}: </span>
            {piece.text}
          </mark>
        ) : (
          <span key={index}>{piece.text}</span>
        ),
      )}
    </span>
  );
}
