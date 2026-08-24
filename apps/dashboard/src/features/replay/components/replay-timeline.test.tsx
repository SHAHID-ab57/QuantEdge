import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ReplayTimeline as ReplayTimelineData } from '../engine/replay-timeline';
import { ReplayTimeline, type ReplayTimelineProps } from './replay-timeline';

afterEach(() => {
  cleanup();
});

function timeline(overrides: Partial<ReplayTimelineData> = {}): ReplayTimelineData {
  return {
    startMs: Date.parse('2026-01-01T00:00:00Z'),
    endMs: Date.parse('2026-01-01T01:00:00Z'),
    currentMs: Date.parse('2026-01-01T00:30:00Z'),
    progress: 50,
    totalCandles: 60,
    position: 31,
    ...overrides,
  };
}

function renderTimeline(overrides: Partial<ReplayTimelineProps> = {}) {
  return render(
    <ReplayTimeline
      timeline={timeline()}
      disabled={false}
      onSeekToProgress={vi.fn()}
      onJumpBack={vi.fn()}
      onJumpForward={vi.fn()}
      onJumpToStart={vi.fn()}
      onJumpToEnd={vi.fn()}
      jumpSize={10}
      {...overrides}
    />,
  );
}

describe('ReplayTimeline', () => {
  it('shows start, current, end, progress percentage, and candle position', () => {
    renderTimeline();
    expect(screen.getByText('50.0% · candle 31 of 60', { exact: false })).toBeInTheDocument();
  });

  it('shows an em dash for start/end/current before any candles are loaded', () => {
    renderTimeline({
      timeline: timeline({
        startMs: null,
        endMs: null,
        currentMs: null,
        totalCandles: 0,
        position: 0,
      }),
      disabled: true,
    });
    expect(screen.getAllByText('—', { exact: false }).length).toBeGreaterThan(0);
  });

  it('shows elapsed and remaining duration across the loaded data’s own time span', () => {
    // 30 minutes elapsed since start (00:00 → 00:30), 30 minutes remaining until end (00:30 → 01:00).
    renderTimeline();
    expect(screen.getByText('Elapsed: 30m 0s')).toBeInTheDocument();
    expect(screen.getByText('Remaining: 30m 0s')).toBeInTheDocument();
  });

  it('shows an em dash for elapsed/remaining before any candles are loaded', () => {
    renderTimeline({
      timeline: timeline({
        startMs: null,
        endMs: null,
        currentMs: null,
        totalCandles: 0,
        position: 0,
      }),
      disabled: true,
    });
    expect(screen.getByText('Elapsed: —')).toBeInTheDocument();
    expect(screen.getByText('Remaining: —')).toBeInTheDocument();
  });

  it('calls onJumpBack/onJumpForward from the jump buttons, labelled with the jump size', () => {
    const onJumpBack = vi.fn();
    const onJumpForward = vi.fn();
    renderTimeline({ onJumpBack, onJumpForward, jumpSize: 25 });
    fireEvent.click(screen.getByRole('button', { name: 'Jump back 25 candles' }));
    fireEvent.click(screen.getByRole('button', { name: 'Jump forward 25 candles' }));
    expect(onJumpBack).toHaveBeenCalledTimes(1);
    expect(onJumpForward).toHaveBeenCalledTimes(1);
  });

  it('calls onJumpToStart/onJumpToEnd from the first/last-page buttons', () => {
    const onJumpToStart = vi.fn();
    const onJumpToEnd = vi.fn();
    renderTimeline({ onJumpToStart, onJumpToEnd });
    fireEvent.click(screen.getByRole('button', { name: 'Jump to start' }));
    fireEvent.click(screen.getByRole('button', { name: 'Jump to end' }));
    expect(onJumpToStart).toHaveBeenCalledTimes(1);
    expect(onJumpToEnd).toHaveBeenCalledTimes(1);
  });

  it('disables the slider and every jump button when disabled', () => {
    renderTimeline({ disabled: true });
    expect(screen.getByRole('slider', { name: 'Replay progress' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Jump back 10 candles' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Jump to start' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Jump to end' })).toBeDisabled();
  });

  it('calls onSeekToProgress when the slider is dragged', () => {
    const onSeekToProgress = vi.fn();
    renderTimeline({ onSeekToProgress });
    const slider = screen.getByRole('slider', { name: 'Replay progress' });
    fireEvent.change(slider, { target: { value: 75 } });
    expect(onSeekToProgress).toHaveBeenCalledWith(75);
  });
});
