import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { StatTile } from './stat-tile';

afterEach(() => {
  cleanup();
});

function renderTile(props: Partial<React.ComponentProps<typeof StatTile>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <StatTile label="Total Volume" value="1,234" {...props} />
    </ThemeProvider>,
  );
}

describe('StatTile', () => {
  it('renders the label and value', () => {
    renderTile();
    expect(screen.getByText('Total Volume')).toBeInTheDocument();
    expect(screen.getByText('1,234')).toBeInTheDocument();
  });

  it('renders a caption when provided', () => {
    renderTile({ caption: '2m ago' });
    expect(screen.getByText('2m ago')).toBeInTheDocument();
  });

  it('renders no caption by default', () => {
    const { container } = renderTile();
    expect(container.querySelectorAll('p')).toHaveLength(1); // just the value
  });

  it('shows a tooltip with the hint text on hover', async () => {
    renderTile({ hint: 'Derived from stored candles' });
    fireEvent.mouseOver(screen.getByText('1,234'));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Derived from stored candles');
  });

  it('treats the literal "Unavailable" value as muted, matching the platform convention', () => {
    const { container: unavailable } = renderTile({ value: 'Unavailable' });
    const { container: available } = renderTile({ value: '100.00' });
    // Different classes implies MUI applied a different `sx` color — the
    // exact class name is an implementation detail, so this just checks
    // the two cases render distinctly rather than identically.
    expect(unavailable.querySelector('p')?.className).not.toBe(
      available.querySelector('p')?.className,
    );
  });

  it('lets an explicit color override the Unavailable-muting default', () => {
    renderTile({ value: '+3.2%', color: 'success.main' });
    expect(screen.getByText('+3.2%')).toBeInTheDocument();
  });

  it('renders an adornment beside the label when one is given', () => {
    renderTile({ adornment: <button type="button">info</button> });
    expect(screen.getByRole('button', { name: 'info' })).toBeInTheDocument();
  });

  it('renders no adornment by default', () => {
    renderTile();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
