import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { ValidationRuleCatalog as ValidationRuleCatalogData } from '@/types/api/dataset-validation';
import { ValidationRuleCatalog } from './validation-rule-catalog';

function catalogue(): ValidationRuleCatalogData {
  return {
    rules: [
      {
        name: 'required_columns',
        category: 'structural',
        description: 'Every required column exists.',
        default_severity: 'error',
        version: '1.0.0',
      },
      {
        name: 'missing_values',
        category: 'data_quality',
        description: 'Null cell counts per column.',
        default_severity: 'warning',
        version: '1.0.0',
      },
    ],
    total: 2,
    categories: ['structural', 'data_quality'],
  };
}

function renderCatalogue(props: Partial<React.ComponentProps<typeof ValidationRuleCatalog>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <ValidationRuleCatalog catalogue={catalogue()} loading={false} {...props} />
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe('ValidationRuleCatalog', () => {
  it('shows a loading skeleton while the catalogue is loading', () => {
    render(
      <ThemeProvider theme={theme}>
        <ValidationRuleCatalog catalogue={undefined} loading />
      </ThemeProvider>,
    );
    expect(document.querySelector('.MuiSkeleton-root')).toBeInTheDocument();
  });

  it('renders nothing when there is no catalogue and loading has finished', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <ValidationRuleCatalog catalogue={undefined} loading={false} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('reports the total check count and category count', () => {
    renderCatalogue();
    expect(screen.getByText('2 checks across 2 categories run by default.')).toBeInTheDocument();
  });

  it('groups rules under their category label', () => {
    renderCatalogue();
    expect(screen.getByText('Structural')).toBeInTheDocument();
    expect(screen.getByText('Data Quality')).toBeInTheDocument();
    expect(screen.getByText('required_columns')).toBeInTheDocument();
    expect(screen.getByText('missing_values')).toBeInTheDocument();
  });

  it('shows each rules description and default severity at a glance', () => {
    renderCatalogue();
    expect(screen.getByText('Every required column exists.')).toBeInTheDocument();
    expect(screen.getByText('error')).toBeInTheDocument();
    expect(screen.getByText('warning')).toBeInTheDocument();
  });
});

describe('ValidationRuleCatalog — expand/collapse', () => {
  it('starts collapsed, hiding why-it-matters/example-failure content', () => {
    renderCatalogue();
    expect(
      screen.queryByText(/Duplicate observations bias statistical models/),
    ).not.toBeInTheDocument();
  });

  it('expands a rule to reveal why it matters and an example failure', () => {
    renderCatalogue({
      catalogue: {
        rules: [
          {
            name: 'duplicate_rows',
            category: 'data_quality',
            description: 'Checks whether identical records exist.',
            default_severity: 'warning',
            version: '1.0.0',
          },
        ],
        total: 1,
        categories: ['data_quality'],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Expand duplicate_rows' }));
    expect(screen.getByText(/Duplicate observations bias statistical models/)).toBeInTheDocument();
    expect(screen.getByText(/stalled market/)).toBeInTheDocument();
  });

  it('collapses again on a second click', async () => {
    renderCatalogue({
      catalogue: {
        rules: [
          {
            name: 'duplicate_rows',
            category: 'data_quality',
            description: 'Checks whether identical records exist.',
            default_severity: 'warning',
            version: '1.0.0',
          },
        ],
        total: 1,
        categories: ['data_quality'],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Expand duplicate_rows' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Collapse duplicate_rows' }));
    await waitFor(() => {
      expect(
        screen.queryByText(/Duplicate observations bias statistical models/),
      ).not.toBeInTheDocument();
    });
  });

  it('degrades gracefully for a rule with no curated knowledge yet', () => {
    renderCatalogue({
      catalogue: {
        rules: [
          {
            name: 'some_future_rule',
            category: 'structural',
            description: 'A rule not yet curated.',
            default_severity: 'error',
            version: '1.0.0',
          },
        ],
        total: 1,
        categories: ['structural'],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Expand some_future_rule' }));
    expect(screen.getAllByText('Not yet documented for this rule.').length).toBe(2);
  });
});
