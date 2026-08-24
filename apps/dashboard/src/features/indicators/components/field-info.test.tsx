import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { FIELD_HELP } from '../lib/field-help';
import { FieldInfo } from './field-info';

afterEach(() => {
  cleanup();
});

describe('FieldInfo', () => {
  it('names the field in its accessible label', () => {
    render(<FieldInfo field="market" label="Market" />);
    expect(screen.getByRole('button', { name: 'About Market' })).toBeInTheDocument();
  });

  it('shows the dictionary content for the given field', async () => {
    render(<FieldInfo field="cacheStatus" label="Cache" />);
    fireEvent.mouseOver(screen.getByRole('button', { name: 'About Cache' }));
    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip).toHaveTextContent(FIELD_HELP.cacheStatus.what);
    expect(tooltip).toHaveTextContent('What it is');
    expect(tooltip).toHaveTextContent('Why it matters');
    expect(tooltip).toHaveTextContent('How to read it');
  });

  it('is keyboard reachable and opens on focus', async () => {
    render(<FieldInfo field="warmupCandles" label="Warmup Candles" />);
    const button = screen.getByRole('button', { name: 'About Warmup Candles' });
    fireEvent.keyDown(document.body, { key: 'Tab' });
    button.focus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent(FIELD_HELP.warmupCandles.what);
  });
});
