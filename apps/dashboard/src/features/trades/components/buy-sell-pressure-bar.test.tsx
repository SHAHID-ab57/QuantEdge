import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { BuySellPressureBar } from './buy-sell-pressure-bar';

afterEach(() => {
  cleanup();
});

describe('BuySellPressureBar', () => {
  it('shows an even split and "Unavailable" percentages with no volume yet', () => {
    render(<BuySellPressureBar label="Pressure" buyVolume={0} sellVolume={0} />);
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.getByRole('meter', { name: 'Pressure' })).not.toHaveAttribute('aria-valuenow');
  });

  it('reports the buy share as a percentage of total volume', () => {
    render(<BuySellPressureBar label="Pressure" buyVolume={3} sellVolume={1} />);
    expect(screen.getByText('75% / 25%')).toBeInTheDocument();
    expect(screen.getByRole('meter', { name: 'Pressure' })).toHaveAttribute('aria-valuenow', '75');
  });

  it('reports all-sell pressure correctly', () => {
    render(<BuySellPressureBar label="Pressure" buyVolume={0} sellVolume={10} />);
    expect(screen.getByText('0% / 100%')).toBeInTheDocument();
  });
});
