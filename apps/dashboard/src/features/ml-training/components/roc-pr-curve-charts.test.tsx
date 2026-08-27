import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { RocPrCurveCharts } from './roc-pr-curve-charts';

afterEach(() => cleanup());

const ROC_PR = {
  curves: {
    up: { roc: { fpr: [0, 1], tpr: [0, 1] }, pr: { precision: [1, 0.5], recall: [0, 1] } },
    down: {
      roc: { fpr: [0, 0.5, 1], tpr: [0, 0.8, 1] },
      pr: { precision: [1, 0.6, 0.5], recall: [0, 0.5, 1] },
    },
  },
  auc: { up: 0.87, down: 0.91 },
  average_precision: { up: 0.8, down: 0.85 },
  macro_auc: 0.89,
};

describe('RocPrCurveCharts', () => {
  it('renders one ROC/PR chart pair and an AUC legend per class', () => {
    render(
      <ThemeProvider theme={theme}>
        <RocPrCurveCharts rocPrCurves={ROC_PR} />
      </ThemeProvider>,
    );
    expect(screen.getByLabelText('ROC curve')).toBeInTheDocument();
    expect(screen.getByLabelText('Precision-Recall curve')).toBeInTheDocument();
    expect(screen.getByText(/up: AUC 0.870/)).toBeInTheDocument();
    expect(screen.getByText(/down: AUC 0.910/)).toBeInTheDocument();
    expect(screen.getByText('Macro AUC: 0.890')).toBeInTheDocument();
  });

  it('renders nothing for a malformed or missing roc_pr_curves value', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <RocPrCurveCharts rocPrCurves={undefined} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
