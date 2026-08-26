import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { EmptyStateNotice } from './empty-state-notice';

afterEach(() => cleanup());

describe('EmptyStateNotice', () => {
  it('renders the title and description', () => {
    render(
      <ThemeProvider theme={theme}>
        <EmptyStateNotice
          icon={<span data-testid="icon" />}
          title="No experiments exist"
          description="Create an experiment first."
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('No experiments exist')).toBeInTheDocument();
    expect(screen.getByText('Create an experiment first.')).toBeInTheDocument();
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('omits the action button when no href is given', () => {
    render(
      <ThemeProvider theme={theme}>
        <EmptyStateNotice
          icon={<span />}
          title="No model adapters registered"
          description="Register one on the backend."
        />
      </ThemeProvider>,
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders an action button linking to the given route', () => {
    render(
      <ThemeProvider theme={theme}>
        <EmptyStateNotice
          icon={<span />}
          title="No experiments exist"
          description="Create an experiment first."
          actionLabel="Create an Experiment"
          actionHref="/experiments"
        />
      </ThemeProvider>,
    );
    const link = screen.getByRole('link', { name: 'Create an Experiment' });
    expect(link).toHaveAttribute('href', '/experiments');
  });
});
