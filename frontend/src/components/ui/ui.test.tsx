import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';
import { strings } from '../../strings';
import { Button } from './Button';
import { CoverageRing } from './CoverageRing';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { Input } from './Input';
import { Select } from './Select';
import { SeverityBadge } from './SeverityBadge';
import { Skeleton, SkeletonGroup } from './Skeleton';
import { StatCard } from './StatCard';
import { coverageTone } from './coverage';
import { SEVERITIES, SEVERITY_STYLES } from './severity';
import { changeTone, formatDelta } from './statCardUtils';

describe('Button', () => {
  it('is a button of type button by default and runs onClick', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });
    expect(button.getAttribute('type')).toBe('button');
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled and busy while loading, with the loading label', () => {
    render(
      <Button loading loadingLabel="Saving">
        Save
      </Button>,
    );
    const button = screen.getByRole('button', { name: 'Saving' });
    expect(button.hasAttribute('disabled')).toBe(true);
    expect(button.getAttribute('aria-busy')).toBe('true');
  });

  it('keeps the label as the accessible name of an icon-only button', () => {
    render(
      <Button iconOnly iconStart={<svg />}>
        Notifications
      </Button>,
    );
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeTruthy();
  });
});

describe('Input', () => {
  it('associates label, hint and error with the control', () => {
    render(<Input label="E-mail" hint="Work address" error="Required" />);
    const input = screen.getByLabelText('E-mail');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    const described = input.getAttribute('aria-describedby') ?? '';
    expect(described.split(' ')).toHaveLength(2);
    expect(screen.getByRole('alert').textContent).toBe('Required');
    expect(screen.getByText('Work address')).toBeTruthy();
  });

  it('has no aria-invalid without an error', () => {
    render(<Input label="Name" />);
    expect(screen.getByLabelText('Name').getAttribute('aria-invalid')).toBeNull();
  });
});

describe('Select', () => {
  it('labels the trigger and shows the chosen option', () => {
    render(
      <Select label="Kind" value="cron" onValueChange={() => undefined} options={[{ value: 'cron', label: 'Cron' }]} />,
    );
    const trigger = screen.getByRole('combobox', { name: 'Kind' });
    expect(trigger.textContent).toContain('Cron');
  });

  it('announces an error', () => {
    render(<Select label="Zone" value={undefined} onValueChange={() => undefined} options={[]} error="Pick one" />);
    expect(screen.getByRole('combobox', { name: 'Zone' }).getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByRole('alert').textContent).toBe('Pick one');
  });
});

describe('SeverityBadge', () => {
  it('shows an icon and the word for every state, never colour alone', () => {
    render(
      <div>
        {SEVERITIES.map((severity) => (
          <SeverityBadge key={severity} severity={severity} />
        ))}
      </div>,
    );
    for (const severity of SEVERITIES) {
      const badge = document.querySelector(`[data-severity="${severity}"]`);
      expect(badge?.textContent).toContain(strings.badge[severity]);
      expect(badge?.querySelector('svg')).toBeTruthy();
      expect(badge?.className).toContain(`co-badge--${SEVERITY_STYLES[severity].tone}`);
    }
  });

  it('maps failed and missed to danger and paused to muted', () => {
    expect(SEVERITY_STYLES.failed.tone).toBe('danger');
    expect(SEVERITY_STYLES.missed.tone).toBe('danger');
    expect(SEVERITY_STYLES.paused.tone).toBe('muted');
    expect(SEVERITY_STYLES.verified.tone).toBe('success');
  });
});

describe('Skeleton', () => {
  it('is hidden from assistive technology and the group announces loading', () => {
    render(
      <SkeletonGroup>
        <Skeleton />
      </SkeletonGroup>,
    );
    expect(document.querySelector('.co-skeleton')?.getAttribute('aria-hidden')).toBe('true');
    expect(screen.getByRole('status').textContent).toContain(strings.states.loading);
  });
});

describe('EmptyState and ErrorState', () => {
  it('renders title, description, steps and action', () => {
    render(<EmptyState title="No clients" description="Add one." steps={['Add', 'Send']} action={<Button>Add</Button>} />);
    expect(screen.getByRole('heading', { name: 'No clients' })).toBeTruthy();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Add' })).toBeTruthy();
  });

  it('shows the request id and a retry button for a server error', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const error = new ApiError({ title: 'Internal Server Error', status: 500, detail: 'Database timeout', request_id: 'req-1' });
    render(<ErrorState error={error} onRetry={onRetry} />);
    expect(screen.getByRole('alert').textContent).toContain('Database timeout');
    expect(screen.getByText('req-1')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: strings.states.retry }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('says the server did not answer for a network error', () => {
    render(<ErrorState error={new ApiError({ title: 'x', status: 0 })} />);
    expect(screen.getByRole('heading').textContent).toBe(strings.states.offlineTitle);
  });
});

describe('StatCard', () => {
  it('shows value, change with a word and the sparkline summary', () => {
    render(<StatCard label="Verified" value={41} delta={3} spark={[1, 2, 3]} />);
    expect(screen.getByText('41')).toBeTruthy();
    expect(screen.getByText(`+3 ${strings.stat.vsYesterday}`)).toBeTruthy();
    expect(screen.getByRole('img', { name: /Verified, last 14 days: 3 points, last 3/ })).toBeTruthy();
  });

  it('renders the loading state as a status', () => {
    render(<StatCard label="Failed" value={null} loading />);
    expect(screen.getByRole('status').textContent).toContain('Failed');
    expect(screen.queryByText('–')).toBeNull();
  });

  it('shows no history when there is no change and no sparkline', () => {
    render(<StatCard label="Unmatched" value={0} />);
    expect(screen.getByRole('img', { name: new RegExp(strings.states.noHistory) })).toBeTruthy();
    expect(screen.queryByText(strings.stat.noChange)).toBeNull();
  });

  it('colours a rise by whether up is good', () => {
    expect(changeTone(2, 'up')).toBe('success');
    expect(changeTone(2, 'down')).toBe('danger');
    expect(changeTone(-1, 'down')).toBe('success');
    expect(changeTone(0, 'up')).toBe('neutral');
    expect(formatDelta(0)).toBe(strings.stat.noChange);
    expect(formatDelta(-4)).toBe(`−4 ${strings.stat.vsYesterday}`);
  });
});

describe('CoverageRing', () => {
  it('names the percentage and the counts', () => {
    render(<CoverageRing verified={46} expected={48} />);
    expect(screen.getByRole('img', { name: /96 percent, 46 of 48 verified/ })).toBeTruthy();
  });

  it('shows the empty state with nothing expected and a status while loading', () => {
    const { unmount } = render(<CoverageRing verified={0} expected={0} />);
    expect(screen.getByRole('img', { name: new RegExp(strings.coverage.none) })).toBeTruthy();
    unmount();
    render(<CoverageRing verified={0} expected={0} loading />);
    expect(screen.getByRole('status')).toBeTruthy();
  });

  it('picks the tone by ratio', () => {
    expect(coverageTone(1, 10)).toBe('success');
    expect(coverageTone(0.85, 10)).toBe('warning');
    expect(coverageTone(0.5, 10)).toBe('danger');
    expect(coverageTone(0, 0)).toBe('muted');
  });
});
