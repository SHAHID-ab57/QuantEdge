import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { MaxRowsSelector } from './max-rows-selector';

afterEach(() => {
  cleanup();
});

describe('MaxRowsSelector', () => {
  it('renders every option and marks the current value selected', () => {
    render(
      <ThemeProvider theme={theme}>
        <MaxRowsSelector value={100} onChange={vi.fn()} />
      </ThemeProvider>,
    );
    for (const rows of [25, 50, 100, 200]) {
      expect(screen.getByRole('button', { name: `${rows} rows` })).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: '100 rows' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('calls onChange with the newly selected value', () => {
    const onChange = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <MaxRowsSelector value={100} onChange={onChange} />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: '25 rows' }));
    expect(onChange).toHaveBeenCalledWith(25);
  });

  it('does not call onChange when clicking the already-selected value', () => {
    const onChange = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <MaxRowsSelector value={100} onChange={onChange} />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: '100 rows' }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
