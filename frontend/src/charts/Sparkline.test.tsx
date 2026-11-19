import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { strings } from '../strings';
import { Sparkline } from './Sparkline';

describe('Sparkline', () => {
  it('draws a line, an area and a last-value dot for many points', () => {
    render(<Sparkline values={[1, 3, 2, 5, 4, 6, 5, 7, 6, 8, 7, 9, 8, 10]} label="Verified" />);
    const svg = screen.getByRole('img', { name: 'Verified: 14 points, last 10' });
    expect(svg.querySelectorAll('path')).toHaveLength(2);
    expect(svg.querySelectorAll('circle')).toHaveLength(1);
  });

  it('draws one dot and no line for a single point', () => {
    render(<Sparkline values={[5]} label="Silent" />);
    const svg = screen.getByRole('img', { name: 'Silent: 1 point, last 5' });
    expect(svg.querySelectorAll('path')).toHaveLength(0);
    expect(svg.querySelectorAll('circle')).toHaveLength(1);
  });

  it('shows a labelled baseline for no points', () => {
    render(<Sparkline values={[]} label="Paused" />);
    const svg = screen.getByRole('img', { name: `Paused: ${strings.states.noHistory}` });
    expect(svg.querySelectorAll('line')).toHaveLength(1);
    expect(svg.textContent).toContain(strings.states.noHistory);
  });

  it('keeps a flat series in the middle instead of on the floor', () => {
    render(<Sparkline values={[4, 4, 4]} label="Flat" height={40} />);
    const dot = screen.getByRole('img').querySelector('circle');
    expect(Number(dot?.getAttribute('cy'))).toBeCloseTo(20, 0);
  });
});
