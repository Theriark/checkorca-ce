import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { strings } from '../strings';
import { BREAKDOWN_VENDOR, makeTrend } from '../test/fixtures';
import { BreakdownBars } from './BreakdownBars';
import { StackedBars } from './StackedBars';
import { niceMax } from './chartUtils';

describe('StackedBars', () => {
  it('draws one stacked bar per day for many days, with the three segments and a legend', () => {
    render(<StackedBars days={makeTrend(30)} label="Last 30 days" />);
    const svg = screen.getByRole('img', { name: /Last 30 days: 30 days/ });
    expect(svg.querySelectorAll('.co-bars__day')).toHaveLength(30);
    expect(svg.querySelectorAll('.co-bars__seg--verified').length).toBe(30);
    expect(svg.querySelectorAll('.co-bars__seg--failed').length).toBeGreaterThan(0);
    expect(svg.querySelectorAll('.co-bars__seg--silent').length).toBeGreaterThan(0);
    expect(screen.getByText(strings.dashboard.stats.silent)).toBeTruthy();
  });

  it('draws a single bar for one day', () => {
    render(<StackedBars days={[{ date: '2026-11-20', verified: 3, failed: 1, silent: 0 }]} label="Trend" />);
    const svg = screen.getByRole('img', { name: 'Trend: 1 day, 3 verified, 1 failed, 0 silent' });
    expect(svg.querySelectorAll('.co-bars__day')).toHaveLength(1);
    expect(svg.querySelectorAll('.co-bars__seg--silent')).toHaveLength(0);
  });

  it('shows a labelled baseline for no days', () => {
    render(<StackedBars days={[]} label="Trend" />);
    const svg = screen.getByRole('img', { name: `Trend: ${strings.states.noHistory}` });
    expect(svg.querySelectorAll('.co-bars__day')).toHaveLength(0);
    expect(svg.textContent).toContain(strings.states.noHistory);
  });

  it('rounds the axis maximum up to a round number', () => {
    expect(niceMax(0)).toBe(1);
    expect(niceMax(1)).toBe(1);
    expect(niceMax(3)).toBe(5);
    expect(niceMax(17)).toBe(20);
    expect(niceMax(50)).toBe(50);
    expect(niceMax(51)).toBe(100);
    expect(niceMax(Number.NaN)).toBe(1);
  });
});

describe('BreakdownBars', () => {
  it('lists the rows busiest first with a bar and the counts in words', () => {
    render(<BreakdownBars items={BREAKDOWN_VENDOR.items} label="Breakdown" />);
    const list = screen.getByRole('list', { name: 'Breakdown' });
    const rows = list.querySelectorAll('.co-bd__row');
    expect(rows).toHaveLength(3);
    expect(rows[0]?.textContent).toContain('Veeam');
    expect(screen.getByRole('img', { name: 'Veeam: 120 verified, 6 failed, 3 silent' })).toBeTruthy();
    // The pack-less row gets its words, not an empty label.
    expect(rows[2]?.textContent).toContain(strings.dashboard.breakdownNoPack);
  });

  it('shows one row for one item and nothing for none', () => {
    const { unmount } = render(<BreakdownBars items={[{ key: 'x', label: 'Only', verified: 0, failed: 0, silent: 0 }]} label="One" />);
    expect(screen.getByRole('list', { name: 'One' }).querySelectorAll('.co-bd__row')).toHaveLength(1);
    expect(screen.getByRole('img', { name: 'Only: 0 verified, 0 failed, 0 silent' }).querySelector('.co-bd__seg--none')).toBeTruthy();
    unmount();
    render(<BreakdownBars items={[]} label="None" />);
    expect(screen.getByRole('list', { name: 'None' }).querySelectorAll('.co-bd__row')).toHaveLength(0);
  });

  it('cuts the list at the limit and says how many rows are left out', () => {
    const items = Array.from({ length: 15 }, (_, index) => ({ key: `k${index}`, label: `Client ${index}`, verified: index, failed: 0, silent: 0 }));
    render(<BreakdownBars items={items} label="Many" limit={12} />);
    expect(screen.getByRole('list', { name: 'Many' }).querySelectorAll('.co-bd__row')).toHaveLength(12);
    expect(screen.getByText(`3 ${strings.chart.more}`)).toBeTruthy();
  });
});
