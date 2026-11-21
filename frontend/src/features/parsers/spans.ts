/** The spans the engine read, cut into the pieces a text renders. */

export interface TextSpan {
  readonly start: number;
  readonly end: number;
  readonly field: string;
  /** 1-based result index. */
  readonly result: number;
}

export interface TextPiece {
  readonly text: string;
  readonly span: TextSpan | null;
}

/** Cut the text at the span edges; a span outside the text is dropped and,
 *  of two overlapping spans, the first (the earlier, then the longer) wins. */
export function splitBySpans(text: string, spans: readonly TextSpan[]): readonly TextPiece[] {
  const sorted = [...spans].filter((span) => span.start < span.end && span.start >= 0 && span.end <= text.length).sort((a, b) => a.start - b.start || b.end - a.end);
  const pieces: TextPiece[] = [];
  let cursor = 0;
  for (const span of sorted) {
    if (span.start < cursor) {
      continue;
    }
    if (span.start > cursor) {
      pieces.push({ text: text.slice(cursor, span.start), span: null });
    }
    pieces.push({ text: text.slice(span.start, span.end), span });
    cursor = span.end;
  }
  if (cursor < text.length) {
    pieces.push({ text: text.slice(cursor), span: null });
  }
  return pieces;
}
