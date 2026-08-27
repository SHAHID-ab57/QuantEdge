import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { ModelMetadataPanel } from './model-metadata-panel';

afterEach(() => cleanup());

describe('ModelMetadataPanel', () => {
  it('renders library versions, timing, memory, and dataset shape', () => {
    render(
      <ThemeProvider theme={theme}>
        <ModelMetadataPanel
          metadata={{
            sklearn_version: '1.5.0',
            joblib_version: '1.4.2',
            training_duration_seconds: 0.123456,
            cpu_time_seconds: 0.1,
            memory_usage_mb: 42.5,
            feature_count: 5,
            sample_count: 100,
          }}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('1.5.0')).toBeInTheDocument();
    expect(screen.getByText('1.4.2')).toBeInTheDocument();
    expect(screen.getByText('42.5 MB')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  it('reports memory as Unknown when not available', () => {
    render(
      <ThemeProvider theme={theme}>
        <ModelMetadataPanel
          metadata={{
            sklearn_version: '1.5.0',
            joblib_version: '1.4.2',
            training_duration_seconds: 0,
            cpu_time_seconds: 0,
            memory_usage_mb: null,
            feature_count: 1,
            sample_count: 1,
          }}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('renders nothing for a malformed metadata value', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <ModelMetadataPanel metadata={undefined} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
