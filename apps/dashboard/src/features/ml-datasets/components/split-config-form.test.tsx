import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { SplitConfigForm } from './split-config-form';

afterEach(() => cleanup());

function renderForm(values = { train: 0.7, validation: 0.15, test: 0.15 }) {
  const onChange = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <SplitConfigForm values={values} onChange={onChange} />
    </ThemeProvider>,
  );
  return onChange;
}

describe('SplitConfigForm', () => {
  it('renders the three ratio fields with their current values', () => {
    renderForm();
    expect(screen.getByLabelText('Train ratio')).toHaveValue(0.7);
    expect(screen.getByLabelText('Validation ratio')).toHaveValue(0.15);
    expect(screen.getByLabelText('Test ratio')).toHaveValue(0.15);
  });

  it('shows the split as a percentage helper text under each field', () => {
    renderForm();
    expect(screen.getByLabelText('Train ratio').closest('.MuiFormControl-root')).toHaveTextContent(
      '70%',
    );
    expect(
      screen.getByLabelText('Validation ratio').closest('.MuiFormControl-root'),
    ).toHaveTextContent('15%');
  });

  it('renders a proportional timeline when the split is valid', () => {
    renderForm();
    expect(screen.getByLabelText('Split timeline')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows an error instead of the timeline when ratios do not sum to 1.0', () => {
    renderForm({ train: 0.5, validation: 0.3, test: 0.3 });
    expect(screen.getByRole('alert')).toHaveTextContent(/sum to 1\.0/);
    expect(screen.queryByLabelText('Split timeline')).not.toBeInTheDocument();
  });

  it('calls onChange with the updated train ratio', () => {
    const onChange = renderForm();
    fireEvent.change(screen.getByLabelText('Train ratio'), { target: { value: '0.8' } });
    expect(onChange).toHaveBeenCalledWith({ train: 0.8, validation: 0.15, test: 0.15 });
  });

  it('shows estimated row counts per split when a total row count is known', () => {
    render(
      <ThemeProvider theme={theme}>
        <SplitConfigForm
          values={{ train: 0.7, validation: 0.15, test: 0.15 }}
          onChange={vi.fn()}
          estimatedTotalRows={1000}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText(/~700 rows/)).toBeInTheDocument();
    expect(screen.getAllByText(/~150 rows/)).toHaveLength(2);
  });

  it('omits estimated row counts before any dataset has been built', () => {
    renderForm();
    expect(screen.queryByText(/rows/)).not.toBeInTheDocument();
  });
});
