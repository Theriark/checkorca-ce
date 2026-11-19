import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { ActionMenu } from './ActionMenu';
import { Alert } from './Alert';
import { CopyField } from './CopyField';
import { FileField } from './FileField';
import { Switch } from './Switch';
import { Tabs } from './Tabs';
import { ToastProvider } from './Toast';

afterEach(() => {
  vi.restoreAllMocks();
});

function SwitchHost() {
  const [on, setOn] = useState(false);
  return <Switch label="Show archived" checked={on} onCheckedChange={setOn} />;
}

describe('Switch', () => {
  it('is a labelled switch that toggles by click and by keyboard', async () => {
    const user = userEvent.setup();
    render(<SwitchHost />);
    const control = screen.getByRole('switch', { name: 'Show archived' });
    expect((control as HTMLInputElement).checked).toBe(false);
    await user.click(screen.getByText('Show archived'));
    expect((control as HTMLInputElement).checked).toBe(true);
    control.focus();
    await user.keyboard(' ');
    expect((control as HTMLInputElement).checked).toBe(false);
  });
});

function TabsHost() {
  const [tab, setTab] = useState('jobs');
  return (
    <Tabs
      label="Client tabs"
      value={tab}
      onValueChange={setTab}
      items={[
        { id: 'jobs', label: 'Jobs', badge: 2, content: <p>Job list</p> },
        { id: 'history', label: 'History', content: <p>History list</p> },
        { id: 'reports', label: 'Reports', content: <p>Report list</p> },
      ]}
    />
  );
}

describe('Tabs', () => {
  it('follows the tabs pattern: one panel, arrow keys, Home and End', async () => {
    const user = userEvent.setup();
    render(<TabsHost />);
    const list = screen.getByRole('tablist', { name: 'Client tabs' });
    const tabs = within(list).getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    expect(tabs[0]?.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').textContent).toBe('Job list');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(tabs[0]?.id);
    await user.click(within(list).getByRole('tab', { name: 'History' }));
    expect(screen.getByRole('tabpanel').textContent).toBe('History list');
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tabpanel').textContent).toBe('Report list');
    expect(document.activeElement).toBe(within(list).getByRole('tab', { name: 'Reports' }));
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tabpanel').textContent).toBe('Job list');
    await user.keyboard('{End}');
    expect(screen.getByRole('tabpanel').textContent).toBe('Report list');
    await user.keyboard('{Home}');
    expect(screen.getByRole('tabpanel').textContent).toBe('Job list');
    // Only the selected tab is in the tab order.
    expect(within(list).getByRole('tab', { name: 'History' }).getAttribute('tabindex')).toBe('-1');
  });
});

describe('CopyField', () => {
  it('copies the value and reports it; a refused clipboard selects the text and says so', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(
      <ToastProvider>
        <CopyField label="Ping URL" value="https://example.com/api/v1/ping/abc" unavailable="Not available." />
      </ToastProvider>,
    );
    expect((screen.getByLabelText('Ping URL') as HTMLInputElement).readOnly).toBe(true);
    await user.click(screen.getByRole('button', { name: strings.common.copy }));
    expect(writeText).toHaveBeenCalledWith('https://example.com/api/v1/ping/abc');
    expect(await screen.findByText(strings.common.copied)).toBeTruthy();

    writeText.mockRejectedValueOnce(new Error('denied'));
    await user.click(screen.getByRole('button', { name: strings.common.copy }));
    expect(await screen.findByText(strings.common.copyFailed)).toBeTruthy();
  });

  it('explains a null value instead of an empty field', () => {
    render(
      <ToastProvider>
        <CopyField label="Ping URL" value={null} unavailable="Only signed-in users see it." />
      </ToastProvider>,
    );
    expect(screen.getByText('Only signed-in users see it.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: strings.common.copy })).toBeNull();
  });
});

describe('FileField', () => {
  it('names the chosen file and reports an error on the labelled control', async () => {
    const user = userEvent.setup();
    const onFileChange = vi.fn();
    const { rerender } = render(<FileField label="CSV file" file={null} onFileChange={onFileChange} accept=".csv" />);
    expect(screen.getByText(strings.importCsv.noFile)).toBeTruthy();
    const input = screen.getByLabelText('CSV file') as HTMLInputElement;
    expect(input.type).toBe('file');
    const file = new File(['client,job\n'], 'jobs.csv', { type: 'text/csv' });
    await user.upload(input, file);
    expect(onFileChange).toHaveBeenCalledWith(file);
    rerender(<FileField label="CSV file" file={file} onFileChange={onFileChange} error="Choose a CSV file first." />);
    expect(screen.getByText('jobs.csv')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('Choose a CSV file first.');
    expect(input.getAttribute('aria-invalid')).toBe('true');
  });
});

describe('Alert', () => {
  it('announces danger at once and the rest politely, always with an icon', () => {
    render(
      <>
        <Alert tone="danger" title="Cannot read">Missing column.</Alert>
        <Alert tone="success">All good.</Alert>
      </>,
    );
    const danger = screen.getByRole('alert');
    expect(danger.textContent).toContain('Cannot read');
    expect(danger.querySelector('svg')).toBeTruthy();
    expect(screen.getByRole('status').textContent).toContain('All good.');
  });
});

describe('ActionMenu', () => {
  it('opens a menu of actions by name and runs the chosen one', async () => {
    const user = userEvent.setup();
    const onPause = vi.fn();
    render(
      <ActionMenu
        label="Actions for Veeam nightly"
        items={[
          { id: 'edit', label: 'Edit', onSelect: () => undefined },
          { id: 'pause', label: 'Pause', onSelect: onPause },
          { id: 'copy', label: 'Copy ping URL', onSelect: () => undefined, disabled: true },
        ]}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Actions for Veeam nightly' }));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getAllByRole('menuitem')).toHaveLength(3);
    expect(within(menu).getByRole('menuitem', { name: 'Copy ping URL' }).getAttribute('aria-disabled')).toBe('true');
    await user.click(within(menu).getByRole('menuitem', { name: 'Pause' }));
    expect(onPause).toHaveBeenCalledTimes(1);
  });
});
