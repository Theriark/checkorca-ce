/** The spans the engine read, cut into the pieces a text renders. */

export interface TextSpan {
  /** Offsets in code points, as the Python engine counts (str indexes). */
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

/** The UTF-16 index of every code point start, plus the text length at the
 *  end, so a code-point offset maps to a JavaScript string index. An emoji
 *  outside the basic plane is one code point and two string units. */
function codePointStarts(text: string): number[] {
  const starts: number[] = [];
  let index = 0;
  for (const char of text) {
    starts.push(index);
    index += char.length;
  }
  starts.push(text.length);
  return starts;
}

/** Cut the text at the span edges; a span outside the text is dropped and,
 *  of two overlapping spans, the first (the earlier, then the longer) wins. */
export function splitBySpans(text: string, spans: readonly TextSpan[]): readonly TextPiece[] {
  const starts = codePointStarts(text);
  const length = starts.length - 1;
  const sorted = [...spans].filter((span) => span.start < span.end && span.start >= 0 && span.end <= length).sort((a, b) => a.start - b.start || b.end - a.end);
  const pieces: TextPiece[] = [];
  let cursor = 0;
  for (const span of sorted) {
    if (span.start < cursor) {
      continue;
    }
    const from = starts[span.start] ?? text.length;
    const to = starts[span.end] ?? text.length;
    if (span.start > cursor) {
      pieces.push({ text: text.slice(starts[cursor] ?? text.length, from), span: null });
    }
    pieces.push({ text: text.slice(from, to), span });
    cursor = span.end;
  }
  if (cursor < length) {
    pieces.push({ text: text.slice(starts[cursor] ?? text.length), span: null });
  }
  return pieces;
}
