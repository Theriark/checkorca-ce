/**
 * Where a pack issue sits in the YAML text. The API answers a JSON Pointer
 * into the pack (/status_rules/2/regex, "" for the whole document); this
 * walks the block structure of the text (key: lines by indentation, "- "
 * items of a sequence) to the line that holds it, so the editor can mark it
 * and the list can say "line 12". A key inside a flow mapping on one line
 * ({name: x, origin: y}) resolves to that line. Nothing here parses YAML in
 * full: a pointer that cannot be followed falls back to the deepest line
 * found, and "" to the first line.
 */

export interface IssueLocation {
  /** 0-based line. */
  readonly line: number;
  /** Character offsets of the line in the text, for an editor mark. */
  readonly from: number;
  readonly to: number;
}

function unescapePointer(segment: string): string {
  return segment.replace(/~1/g, '/').replace(/~0/g, '~');
}

/** The segments of a JSON Pointer; [] for the whole document. */
export function pointerSegments(path: string): readonly string[] {
  if (!path || path === '/') {
    return [];
  }
  return path.split('/').slice(1).map(unescapePointer);
}

function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}

function isBlank(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.length === 0 || trimmed.startsWith('#');
}

/** The lines of a block container that starts after `start` (exclusive) and
 *  holds entries deeper than `indent`; stops at the first entry at or above
 *  that indentation. */
function childLines(lines: readonly string[], start: number, indent: number): number[] {
  const found: number[] = [];
  let childIndent: number | null = null;
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index] ?? '';
    if (isBlank(line)) {
      continue;
    }
    const depth = indentOf(line);
    if (depth <= indent) {
      break;
    }
    if (childIndent === null) {
      childIndent = depth;
    }
    if (depth === childIndent) {
      found.push(index);
    }
  }
  return found;
}

/** The line of a pointer in the YAML text, or null for the whole document. */
export function locateIssue(text: string, path: string): IssueLocation | null {
  const segments = pointerSegments(path);
  const lines = text.split('\n');
  const offsetOf = (line: number) => {
    let from = 0;
    for (let index = 0; index < line; index += 1) {
      from += (lines[index] ?? '').length + 1;
    }
    return { line, from, to: from + (lines[line] ?? '').length };
  };
  if (segments.length === 0) {
    return null;
  }
  // The root: its entries are the lines at the smallest indentation.
  let current = -1;
  let indent = -1;
  for (const segment of segments) {
    const children = childLines(lines, current, indent);
    if (children.length === 0) {
      break;
    }
    const first = lines[children[0] ?? 0] ?? '';
    const sequence = first.trimStart().startsWith('- ');
    let next: number | undefined;
    if (sequence && /^\d+$/.test(segment)) {
      next = children[Number(segment)];
    } else {
      next = children.find((index) => {
        const trimmed = (lines[index] ?? '').trimStart().replace(/^- /, '');
        return trimmed.startsWith(`${segment}:`) || trimmed.startsWith(`'${segment}':`) || trimmed.startsWith(`"${segment}":`);
      });
    }
    if (next === undefined) {
      break;
    }
    current = next;
    indent = indentOf(lines[next] ?? '');
    // A sequence item "- key: value" opens a mapping whose other keys sit two
    // columns deeper; its own first key is on the item line.
    if ((lines[next] ?? '').trimStart().startsWith('- ')) {
      indent += 1;
    }
  }
  if (current < 0) {
    return null;
  }
  return offsetOf(current);
}

/** "/status_rules/2/regex" as words: "status_rules › 2 › regex". */
export function describePointer(path: string): string {
  return pointerSegments(path).join(' › ');
}
