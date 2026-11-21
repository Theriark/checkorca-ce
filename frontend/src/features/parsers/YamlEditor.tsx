/**
 * The Pack YAML editor on CodeMirror 6, bundled with the app (no CDN; the
 * server's CSP allows scripts from 'self' only). YAML syntax colours, line
 * numbers, history, Tab indents (Escape then Tab leaves the editor, which
 * CodeMirror announces), and the pack issues of a failed save as lint marks
 * at their line. Read-only for a built-in pack. The syntax colours are the
 * tok- classes of the class highlighter, styled in features.css from the
 * design tokens, so both themes pass contrast (the default highlight style
 * has fixed light-theme colours). The content is always a tab stop (tabindex
 * 0): a read-only contenteditable is not one by itself, and the scrolling
 * text must be reachable from the keyboard whether it is editable or not.
 */
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { yaml } from '@codemirror/lang-yaml';
import { bracketMatching, syntaxHighlighting } from '@codemirror/language';
import { lintGutter, setDiagnostics, type Diagnostic } from '@codemirror/lint';
import { Compartment, EditorState } from '@codemirror/state';
import { EditorView, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers } from '@codemirror/view';
import { classHighlighter } from '@lezer/highlight';
import { useEffect, useRef } from 'react';

import '../features.css';

export interface EditorMark {
  readonly from: number;
  readonly to: number;
  readonly message: string;
}

export interface YamlEditorProps {
  readonly value: string;
  readonly onChange?: (value: string) => void;
  readonly readOnly?: boolean;
  /** The accessible name of the text box. */
  readonly label: string;
  readonly marks?: readonly EditorMark[];
  readonly id?: string;
}

/** Read-only means not editable either (no caret, no input). */
function editability(readOnly: boolean) {
  return [EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)];
}

export function YamlEditor({ value, onChange, readOnly = false, label, marks = [], id }: YamlEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const readOnlyCompartment = useRef(new Compartment());
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!host.current) {
      return undefined;
    }
    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightActiveLine(),
        history(),
        bracketMatching(),
        lintGutter(),
        yaml(),
        syntaxHighlighting(classHighlighter),
        keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
        readOnlyCompartment.current.of(editability(readOnly)),
        EditorView.lineWrapping,
        EditorView.contentAttributes.of({ 'aria-label': label, tabindex: '0', ...(id ? { id } : {}) }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            onChangeRef.current?.(update.state.doc.toString());
          }
        }),
      ],
    });
    const editor = new EditorView({ state, parent: host.current });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
    // The editor is created once; later props are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A value from outside (a reload, a discard) replaces the document; the
  // editor's own edits already match the value.
  useEffect(() => {
    const editor = view.current;
    if (!editor) {
      return;
    }
    const current = editor.state.doc.toString();
    if (current !== value) {
      editor.dispatch({ changes: { from: 0, to: current.length, insert: value } });
    }
  }, [value]);

  useEffect(() => {
    view.current?.dispatch({ effects: readOnlyCompartment.current.reconfigure(editability(readOnly)) });
  }, [readOnly]);

  useEffect(() => {
    const editor = view.current;
    if (!editor) {
      return;
    }
    const length = editor.state.doc.length;
    const diagnostics: Diagnostic[] = marks
      .filter((mark) => mark.from <= length)
      .map((mark) => ({ from: mark.from, to: Math.min(mark.to, length), severity: 'error', message: mark.message }));
    editor.dispatch(setDiagnostics(editor.state, diagnostics));
  }, [marks]);

  return <div ref={host} className={readOnly ? 'co-yaml co-yaml--readonly' : 'co-yaml'} data-testid="yaml-editor" />;
}
