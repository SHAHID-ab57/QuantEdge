import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { ValidationIssue } from '@/types/api/dataset-validation';
import { ValidationIssueList } from './validation-issue-list';

function issue(overrides: Partial<ValidationIssue> = {}): ValidationIssue {
  return {
    rule: 'duplicate_timestamps',
    category: 'data_quality',
    severity: 'error',
    code: 'duplicate_timestamps',
    message: '2 timestamp(s) appear more than once',
    column: null,
    row_index: null,
    count: 2,
    details: {},
    ...overrides,
  };
}

function renderList(props: Partial<React.ComponentProps<typeof ValidationIssueList>>) {
  return render(
    <ThemeProvider theme={theme}>
      <ValidationIssueList issues={[]} emptyMessage="Nothing here." {...props} />
    </ThemeProvider>,
  );
}

let writeText: ReturnType<typeof vi.fn>;

beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
});

afterEach(() => cleanup());

describe('ValidationIssueList', () => {
  it('shows the empty message when there are no issues', () => {
    renderList({ issues: [] });
    expect(screen.getByRole('status')).toHaveTextContent('Nothing here.');
  });

  it('renders every issue given to it, mixed severities included', () => {
    renderList({
      issues: [
        issue({ severity: 'error', code: 'an_error', message: 'an error' }),
        issue({ severity: 'warning', code: 'a_warning', message: 'a warning' }),
      ],
    });
    expect(screen.getByText('an error')).toBeInTheDocument();
    expect(screen.getByText('a warning')).toBeInTheDocument();
  });

  it('shows column, row, and count details when present', () => {
    renderList({ issues: [issue({ column: 'close', row_index: 5, count: 3 })] });
    expect(screen.getByText(/column: close/)).toBeInTheDocument();
    expect(screen.getByText(/row: 5/)).toBeInTheDocument();
    expect(screen.getByText(/count: 3/)).toBeInTheDocument();
  });

  it('omits the detail line entirely when nothing is present', () => {
    renderList({
      issues: [issue({ column: null, row_index: null, count: null, rule: 'x', code: 'y' })],
    });
    expect(screen.queryByText(/column:/)).not.toBeInTheDocument();
    expect(screen.getByText(/rule: x/)).toBeInTheDocument();
  });
});

describe('ValidationIssueList — expand/collapse', () => {
  it('starts collapsed, hiding the suggested fix', () => {
    renderList({ issues: [issue()] });
    expect(screen.queryByText(/Suggested fix:/)).not.toBeInTheDocument();
  });

  it('expands to reveal affected column, row, and a suggested fix', () => {
    renderList({
      issues: [issue({ code: 'duplicate_timestamps', column: 'close', row_index: 2 })],
    });
    fireEvent.click(screen.getByRole('button', { name: 'Expand issue: duplicate_timestamps' }));
    expect(screen.getByText('Affected column:')).toBeInTheDocument();
    expect(screen.getByText('close')).toBeInTheDocument();
    expect(screen.getByText('Affected row:')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText(/Re-run market data validation/)).toBeInTheDocument();
  });

  it('shows an em dash when a field has no value', () => {
    renderList({ issues: [issue({ column: null, row_index: null })] });
    fireEvent.click(screen.getByRole('button', { name: /Expand issue/ }));
    expect(screen.getAllByText('—').length).toBe(2);
  });

  it('honors defaultExpanded, starting every row already open', () => {
    renderList({ issues: [issue()], defaultExpanded: true });
    expect(screen.getByText(/Suggested fix:/)).toBeInTheDocument();
  });

  it('collapses again on a second click', async () => {
    renderList({ issues: [issue()] });
    fireEvent.click(screen.getByRole('button', { name: /Expand issue/ }));
    fireEvent.click(await screen.findByRole('button', { name: /Collapse issue/ }));
    await waitFor(() => {
      expect(screen.queryByText(/Suggested fix:/)).not.toBeInTheDocument();
    });
  });
});

describe('ValidationIssueList — copy issue', () => {
  it('copies a structured summary of the issue to the clipboard', async () => {
    renderList({ issues: [issue({ code: 'duplicate_timestamps', column: 'close' })] });
    fireEvent.click(screen.getByRole('button', { name: 'Copy issue: duplicate_timestamps' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0]![0] as string;
    expect(copied).toContain('Rule: duplicate_timestamps');
    expect(copied).toContain('Severity: error');
    expect(copied).toContain('Affected column: close');
    expect(copied).toContain('Suggested fix:');
  });

  it('shows a brief confirmation after copying', async () => {
    renderList({ issues: [issue({ code: 'duplicate_timestamps' })] });
    fireEvent.click(screen.getByRole('button', { name: 'Copy issue: duplicate_timestamps' }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
  });
});
