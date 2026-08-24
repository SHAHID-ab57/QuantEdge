import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { ReplayTimeline } from '../engine/replay-timeline';
import { ReplayStatus, type ReplayStatusProps } from './replay-status';

afterEach(() => {
  cleanup();
});

function emptyTimeline(): ReplayTimeline {
  return { startMs: null, endMs: null, currentMs: null, progress: 0, totalCandles: 0, position: 0 };
}

function loadedTimeline(overrides: Partial<ReplayTimeline> = {}): ReplayTimeline {
  return {
    startMs: Date.parse('2026-01-01T00:00:00Z'),
    endMs: Date.parse('2026-01-01T01:00:00Z'),
    currentMs: Date.parse('2026-01-01T00:10:00Z'),
    progress: 16.7,
    totalCandles: 60,
    position: 10,
    ...overrides,
  };
}

function renderStatus(overrides: Partial<ReplayStatusProps> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <ReplayStatus
        phase="paused"
        error={null}
        truncated={false}
        onRetry={vi.fn()}
        timeline={emptyTimeline()}
        speed={1}
        {...overrides}
      />
    </ThemeProvider>,
  );
}

describe('ReplayStatus', () => {
  it('shows a chip labelled for each phase', () => {
    renderStatus({ phase: 'playing' });
    expect(screen.getByText('Playing')).toBeInTheDocument();
  });

  it('shows a loading indicator while loading', () => {
    renderStatus({ phase: 'loading' });
    expect(screen.getByText('Loading…')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Loading replay session' })).toBeInTheDocument();
  });

  it('shows the error message and a retry action when in the error phase', () => {
    const onRetry = vi.fn();
    renderStatus({ phase: 'error', error: 'Backend unavailable', onRetry });
    expect(screen.getByRole('alert')).toHaveTextContent('Backend unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('shows no error alert outside the error phase', () => {
    renderStatus({ phase: 'paused' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows a truncation notice when the session was cut short', () => {
    renderStatus({ truncated: true });
    expect(screen.getByText(/cut off before the full range loaded/)).toBeInTheDocument();
  });

  it('shows every phase label distinctly', () => {
    const phases = [
      'idle',
      'loading',
      'playing',
      'paused',
      'seeking',
      'completed',
      'error',
    ] as const;
    const labels = new Set<string>();
    for (const phase of phases) {
      const { unmount } = renderStatus({ phase });
      labels.add(screen.getByText(/./, { selector: '.MuiChip-label' }).textContent ?? '');
      unmount();
    }
    expect(labels.size).toBe(phases.length);
  });

  it('renders no status figures before a session is loaded', () => {
    renderStatus({ phase: 'idle' });
    expect(screen.queryByRole('status', { name: 'Replay status' })).not.toBeInTheDocument();
  });

  it('shows current candle position, loaded, and remaining candle counts', () => {
    renderStatus({ timeline: loadedTimeline({ position: 10, totalCandles: 60 }) });
    expect(screen.getByText('10 of 60')).toBeInTheDocument();
    expect(screen.getByText('60', { selector: 'p' })).toBeInTheDocument(); // loaded
    expect(screen.getByText('50', { selector: 'p' })).toBeInTheDocument(); // remaining = 60 - 10
  });

  it('shows the replay time as the current candle’s own timestamp', () => {
    renderStatus({
      timeline: loadedTimeline({ currentMs: Date.parse('2026-06-15T12:00:00Z') }),
    });
    const panel = screen.getByRole('status', { name: 'Replay status' });
    expect(panel).toHaveTextContent('2026'); // the formatted date is locale-dependent; year is a stable substring
  });

  it('shows the current playback speed', () => {
    renderStatus({ timeline: loadedTimeline(), speed: 5 });
    expect(screen.getByText('5x')).toBeInTheDocument();
  });

  it('shows an estimated completion duration while playing or paused', () => {
    renderStatus({
      phase: 'playing',
      timeline: loadedTimeline({ position: 1, totalCandles: 2 }),
      speed: 1,
    });
    // One candle remaining at 1x (1000ms/tick) → "1s".
    expect(screen.getByText('1s')).toBeInTheDocument();
  });

  it('shows Unavailable for estimated completion once replay has finished', () => {
    renderStatus({
      phase: 'completed',
      timeline: loadedTimeline({ position: 60, totalCandles: 60 }),
    });
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
  });

  it('marks estimated completion as done once no candles remain while still active', () => {
    renderStatus({
      phase: 'paused',
      timeline: loadedTimeline({ position: 60, totalCandles: 60 }),
    });
    expect(screen.getByText('0s')).toBeInTheDocument();
  });
});
