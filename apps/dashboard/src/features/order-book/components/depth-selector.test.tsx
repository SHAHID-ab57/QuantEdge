import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { DepthSelector } from './depth-selector';

afterEach(() => {
  cleanup();
});

describe('DepthSelector', () => {
  it('renders every depth option and marks the current value selected', () => {
    render(
      <ThemeProvider theme={theme}>
        <DepthSelector value={25} onChange={vi.fn()} />
      </ThemeProvider>,
    );
    for (const depth of [10, 25, 50, 100]) {
      expect(screen.getByRole('button', { name: `${depth} levels` })).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: '25 levels' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('calls onChange with the newly selected depth', () => {
    const onChange = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <DepthSelector value={25} onChange={onChange} />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: '100 levels' }));
    expect(onChange).toHaveBeenCalledWith(100);
  });

  it('does not call onChange when clicking the already-selected value', () => {
    const onChange = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <DepthSelector value={25} onChange={onChange} />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: '25 levels' }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
