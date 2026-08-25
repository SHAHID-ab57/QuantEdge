import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { RequiredColumnPresets } from './required-column-presets';

afterEach(() => cleanup());

function renderPresets(props: Partial<React.ComponentProps<typeof RequiredColumnPresets>> = {}) {
  const onApply = vi.fn();
  const utils = render(
    <ThemeProvider theme={theme}>
      <RequiredColumnPresets onApply={onApply} {...props} />
    </ThemeProvider>,
  );
  return { ...utils, onApply };
}

describe('RequiredColumnPresets', () => {
  it('lists every documented preset', () => {
    renderPresets();
    expect(screen.getByText('Raw Market Data')).toBeInTheDocument();
    expect(screen.getByText('OHLCV Only')).toBeInTheDocument();
    expect(screen.getByText('Trend Indicators')).toBeInTheDocument();
    expect(screen.getByText('AI Basic Features')).toBeInTheDocument();
    expect(screen.getByText('Full Dataset')).toBeInTheDocument();
  });

  it('applies the clicked preset', () => {
    const { onApply } = renderPresets();
    fireEvent.click(screen.getByRole('button', { name: 'Apply Full Dataset preset' }));
    expect(onApply).toHaveBeenCalledWith('full_dataset');
  });

  it('disables every preset when asked', () => {
    renderPresets({ disabled: true });
    expect(screen.getByRole('button', { name: 'Apply OHLCV Only preset' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });
});
