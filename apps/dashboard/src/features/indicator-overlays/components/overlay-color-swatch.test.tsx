import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { OverlayColorSwatch } from './overlay-color-swatch';

afterEach(() => {
  cleanup();
});

describe('OverlayColorSwatch', () => {
  it('opens a palette menu when clicked', () => {
    render(
      <ThemeProvider theme={theme}>
        <OverlayColorSwatch
          color="#2196f3"
          label="SMA(20)"
          isOverride={false}
          onSelect={vi.fn()}
          onReset={vi.fn()}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: "Change SMA(20)'s color" }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getByText('primary')).toBeInTheDocument();
    expect(screen.getByText('secondary')).toBeInTheDocument();
  });

  it('calls onSelect with the chosen swatch color', () => {
    const onSelect = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <OverlayColorSwatch
          color="#2196f3"
          label="SMA(20)"
          isOverride={false}
          onSelect={onSelect}
          onReset={vi.fn()}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: "Change SMA(20)'s color" }));
    fireEvent.click(screen.getByText('secondary'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0]![0]).toMatch(/^#/);
  });

  it('disables "Reset to automatic" when there is no override', () => {
    render(
      <ThemeProvider theme={theme}>
        <OverlayColorSwatch
          color="#2196f3"
          label="SMA(20)"
          isOverride={false}
          onSelect={vi.fn()}
          onReset={vi.fn()}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: "Change SMA(20)'s color" }));
    expect(screen.getByRole('menuitem', { name: 'Reset to automatic' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('calls onReset when "Reset to automatic" is clicked with an active override', () => {
    const onReset = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <OverlayColorSwatch
          color="#ff00ff"
          label="SMA(20)"
          isOverride
          onSelect={vi.fn()}
          onReset={onReset}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: "Change SMA(20)'s color" }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reset to automatic' }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });
});
