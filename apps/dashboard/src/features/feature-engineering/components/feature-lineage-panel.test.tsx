import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { FeatureLineage } from '@/types/api/features';
import { FeatureLineagePanel } from './feature-lineage-panel';

afterEach(() => cleanup());

describe('FeatureLineagePanel', () => {
  it('notes that nothing depends on anything when the graph has no edges', () => {
    const lineage: FeatureLineage = {
      nodes: [
        {
          name: 'ohlcv',
          label: 'OHLCV',
          category: 'raw',
          dependencies: [],
          depended_on_by: [],
          ancestors: [],
          descendants: [],
        },
      ],
      edges: [],
      topological_order: ['ohlcv'],
    };
    render(
      <ThemeProvider theme={theme}>
        <FeatureLineagePanel lineage={lineage} />
      </ThemeProvider>,
    );
    expect(screen.getByText(/No registered feature declares a dependency/)).toBeInTheDocument();
    expect(screen.getByText('OHLCV')).toBeInTheDocument();
    expect(screen.getByText('Computation order: ohlcv')).toBeInTheDocument();
  });

  it('renders dependency and dependent chips when edges exist', () => {
    const lineage: FeatureLineage = {
      nodes: [
        {
          name: 'sma',
          label: 'SMA',
          category: 'trend',
          dependencies: [],
          depended_on_by: ['bollinger'],
          ancestors: [],
          descendants: ['bollinger'],
        },
        {
          name: 'bollinger',
          label: 'Bollinger Bands',
          category: 'trend',
          dependencies: ['sma'],
          depended_on_by: [],
          ancestors: ['sma'],
          descendants: [],
        },
      ],
      edges: [['sma', 'bollinger']],
      topological_order: ['sma', 'bollinger'],
    };
    render(
      <ThemeProvider theme={theme}>
        <FeatureLineagePanel lineage={lineage} />
      </ThemeProvider>,
    );
    expect(screen.getAllByText('sma').length).toBeGreaterThan(0);
    expect(screen.getByText('bollinger')).toBeInTheDocument();
    expect(screen.getByText('Computation order: sma → bollinger')).toBeInTheDocument();
  });

  it('renders nothing with no nodes', () => {
    const lineage: FeatureLineage = { nodes: [], edges: [], topological_order: [] };
    const { container } = render(
      <ThemeProvider theme={theme}>
        <FeatureLineagePanel lineage={lineage} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
