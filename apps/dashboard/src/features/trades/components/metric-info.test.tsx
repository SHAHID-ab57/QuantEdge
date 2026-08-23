import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { METRIC_HELP } from '../lib/metric-help';
import { MetricInfo } from './metric-info';

afterEach(() => {
  cleanup();
});

describe('MetricInfo', () => {
  it('names the metric in its accessible label rather than a bare "info"', () => {
    render(<MetricInfo metric="sessionVwap" label="Session VWAP" />);
    expect(screen.getByRole('button', { name: 'About Session VWAP' })).toBeInTheDocument();
  });

  it('is keyboard reachable — it is a real button, not a decorative icon', () => {
    render(<MetricInfo metric="sessionVwap" label="Session VWAP" />);
    const button = screen.getByRole('button', { name: 'About Session VWAP' });
    button.focus();
    expect(button).toHaveFocus();
  });

  it('opens the explanation on keyboard focus, not just on hover', async () => {
    render(<MetricInfo metric="sessionVwap" label="Session VWAP" />);
    const button = screen.getByRole('button', { name: 'About Session VWAP' });
    // MUI opens a tooltip on `:focus-visible`, which is only set for
    // keyboard-driven focus — hence the Tab keydown before focusing, rather
    // than a bare `fireEvent.focus` (which jsdom never treats as visible).
    fireEvent.keyDown(document.body, { key: 'Tab' });
    button.focus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent(METRIC_HELP.sessionVwap.what);
  });

  it('shows what / why / how / how-to-read for a metric that defines all four', async () => {
    render(<MetricInfo metric="buySellImbalance" label="Buy/Sell Imbalance" />);
    fireEvent.mouseOver(screen.getByRole('button', { name: 'About Buy/Sell Imbalance' }));
    const tooltip = await screen.findByRole('tooltip');
    for (const heading of [
      'What it is',
      'Why it matters',
      "How it's calculated",
      'How to read it',
    ]) {
      expect(tooltip).toHaveTextContent(heading);
    }
    expect(tooltip).toHaveTextContent(METRIC_HELP.buySellImbalance.how);
  });

  it('omits the calculation section for a metric that has none', async () => {
    render(<MetricInfo metric="currentPrice" label="Current Price" />);
    fireEvent.mouseOver(screen.getByRole('button', { name: 'About Current Price' }));
    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip).toHaveTextContent('What it is');
    expect(tooltip).not.toHaveTextContent("How it's calculated");
  });
});
