import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { Sparkline } from './sparkline';

afterEach(() => {
  cleanup();
});

describe('Sparkline', () => {
  it('renders an accessible placeholder line with fewer than two data points', () => {
    render(<Sparkline values={[]} ariaLabel="Test metric" />);
    expect(
      screen.getByRole('img', { name: 'Test metric: not enough data yet' }),
    ).toBeInTheDocument();
  });

  it('renders a placeholder when every value is null', () => {
    render(<Sparkline values={[null, null, null]} ariaLabel="Test metric" />);
    expect(
      screen.getByRole('img', { name: 'Test metric: not enough data yet' }),
    ).toBeInTheDocument();
  });

  it('renders a line path once there are at least two known values', () => {
    render(<Sparkline values={[1, 2, 3]} ariaLabel="Test metric" />);
    const svg = screen.getByRole('img', { name: 'Test metric' });
    expect(svg.querySelector('path')).toBeInTheDocument();
  });

  it('skips null gaps rather than treating them as zero', () => {
    render(<Sparkline values={[1, null, 3]} ariaLabel="Test metric" />);
    const svg = screen.getByRole('img', { name: 'Test metric' });
    const path = svg.querySelector('path');
    // Two drawn points (the nulls produce no command), not three.
    expect(path?.getAttribute('d')?.split(' ')).toHaveLength(2);
  });

  it('draws a flat centered line when every known value is identical', () => {
    render(<Sparkline values={[5, 5, 5]} ariaLabel="Test metric" height={40} />);
    const svg = screen.getByRole('img', { name: 'Test metric' });
    const path = svg.querySelector('path');
    expect(path?.getAttribute('d')).toContain('20.00');
  });
});
