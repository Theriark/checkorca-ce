import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { Button } from './Button';
import { CommandSearch, type CommandItem } from './CommandSearch';
import { Dialog } from './Dialog';
import { ToastProvider } from './Toast';
import { filterCommands } from './commandFilter';
import { useToast } from './useToast';

function DialogHost() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <Button onClick={() => setOpen(true)}>Open</Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Pause job"
        description="Stops expecting results."
        footer={<Button onClick={() => setOpen(false)}>Done</Button>}
      >
        <input aria-label="Until" />
      </Dialog>
    </div>
  );
}

describe('Dialog', () => {
  it('opens labelled by its title, traps focus and closes on Escape', async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByRole('button', { name: 'Open' }));
    const dialog = await screen.findByRole('dialog', { name: 'Pause job' });
    expect(dialog.getAttribute('aria-describedby')).toBeTruthy();
    expect(within(dialog).getByLabelText('Until')).toBe(document.activeElement);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('closes with its close button', async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByRole('button', { name: 'Open' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: strings.dialog.close }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

function ToastHost() {
  const { toast } = useToast();
  return (
    <div>
      <Button onClick={() => toast({ tone: 'success', title: 'Saved' })}>success</Button>
      <Button onClick={() => toast({ tone: 'danger', title: 'Export failed', description: 'req-1' })}>danger</Button>
    </div>
  );
}

describe('Toast', () => {
  it('shows a toast with a word and an icon for its tone, and dismisses it', async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ToastHost />
      </ToastProvider>,
    );
    await user.click(screen.getByRole('button', { name: 'danger' }));
    const toast = (await screen.findByText('Export failed')).closest('.co-toast') as HTMLElement;
    expect(toast.textContent).toContain('Failed');
    expect(toast.textContent).toContain('Export failed');
    expect(toast.querySelector('svg')).toBeTruthy();
    await user.click(within(toast).getByRole('button', { name: strings.toast.dismiss }));
    expect(document.querySelector('.co-toast')).toBeNull();
  });
});

const ITEMS: readonly CommandItem[] = [
  { id: 'clients', label: 'Clients', group: 'sections', keywords: ['/clients'], run: vi.fn() },
  { id: 'jobs', label: 'Jobs', group: 'sections', keywords: ['/jobs'], run: vi.fn() },
  { id: 'theme', label: 'Switch to dark theme', group: 'actions', keywords: ['theme'], run: vi.fn() },
];

function SearchHost() {
  const [open, setOpen] = useState(true);
  return <CommandSearch items={ITEMS} open={open} onOpenChange={setOpen} />;
}

describe('CommandSearch', () => {
  it('filters by label and keywords', () => {
    expect(filterCommands(ITEMS, '').map((item) => item.id)).toEqual(['clients', 'jobs', 'theme']);
    expect(filterCommands(ITEMS, 'JOB').map((item) => item.id)).toEqual(['jobs']);
    expect(filterCommands(ITEMS, '/cli').map((item) => item.id)).toEqual(['clients']);
    expect(filterCommands(ITEMS, 'zzz')).toEqual([]);
  });

  it('focuses the input, moves with the arrows and runs the item on Enter', async () => {
    const user = userEvent.setup();
    render(<SearchHost />);
    const input = await screen.findByRole('combobox', { name: strings.search.label });
    expect(input).toBe(document.activeElement);
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(screen.getByRole('option', { name: 'Clients' }).getAttribute('aria-selected')).toBe('true');
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('option', { name: 'Jobs' }).getAttribute('aria-selected')).toBe('true');
    expect(input.getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', { name: 'Jobs' }).id);
    await user.keyboard('{Enter}');
    expect(ITEMS[1]?.run).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('moves up with wrap-around, and jumps with Home and End', async () => {
    const user = userEvent.setup();
    render(<SearchHost />);
    const input = await screen.findByRole('combobox', { name: strings.search.label });
    const selected = () => screen.getAllByRole('option').find((option) => option.getAttribute('aria-selected') === 'true')?.textContent;
    expect(selected()).toBe('Clients');
    // ArrowUp from the first item wraps to the last.
    await user.keyboard('{ArrowUp}');
    expect(selected()).toBe('Switch to dark theme');
    await user.keyboard('{ArrowUp}');
    expect(selected()).toBe('Jobs');
    await user.keyboard('{Home}');
    expect(selected()).toBe('Clients');
    await user.keyboard('{End}');
    expect(selected()).toBe('Switch to dark theme');
    expect(input.getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', { name: 'Switch to dark theme' }).id);
    // ArrowDown from the last wraps to the first; Enter runs it.
    await user.keyboard('{ArrowDown}');
    expect(selected()).toBe('Clients');
    await user.keyboard('{Enter}');
    expect(ITEMS[0]?.run).toHaveBeenCalledTimes(1);
  });

  it('keeps Home and End harmless with no results', async () => {
    const user = userEvent.setup();
    render(<SearchHost />);
    await user.type(await screen.findByRole('combobox'), 'zzz');
    await user.keyboard('{Home}{End}{ArrowUp}{ArrowDown}{Enter}');
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('shows the no-results message', async () => {
    const user = userEvent.setup();
    render(<SearchHost />);
    await user.type(await screen.findByRole('combobox'), 'nothing');
    expect(screen.getByText(strings.search.noResults)).toBeTruthy();
    expect(screen.queryAllByRole('option')).toHaveLength(0);
  });
});
