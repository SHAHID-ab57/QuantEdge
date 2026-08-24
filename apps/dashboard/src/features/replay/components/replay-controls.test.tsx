import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReplayControls, type ReplayControlsProps } from './replay-controls';

afterEach(() => {
  cleanup();
});

function handlers(): Omit<ReplayControlsProps, 'phase' | 'speed'> {
  return {
    onPlay: vi.fn(),
    onResume: vi.fn(),
    onPause: vi.fn(),
    onStop: vi.fn(),
    onRestart: vi.fn(),
    onNext: vi.fn(),
    onPrevious: vi.fn(),
    onSpeedChange: vi.fn(),
  };
}

describe('ReplayControls', () => {
  it('shows Play (disabled) while nothing is loaded', () => {
    const props = handlers();
    render(<ReplayControls phase="idle" speed={1} {...props} />);
    expect(screen.getByRole('button', { name: 'Play' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous candle' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next candle' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled();
  });

  it('calls onPlay when Play is clicked from paused', () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={1} {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(props.onResume).toHaveBeenCalledTimes(1);
    expect(props.onPlay).not.toHaveBeenCalled();
  });

  it('shows Pause (not Play/Resume) while playing, and calls onPause', () => {
    const props = handlers();
    render(<ReplayControls phase="playing" speed={1} {...props} />);
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resume' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
    expect(props.onPause).toHaveBeenCalledTimes(1);
  });

  it('shows Play (not Resume) after completion, restarting from zero', () => {
    const props = handlers();
    render(<ReplayControls phase="completed" speed={1} {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Play' }));
    expect(props.onPlay).toHaveBeenCalledTimes(1);
  });

  it('disables Next/Previous while playing (manual stepping is for paused sessions)', () => {
    const props = handlers();
    render(<ReplayControls phase="playing" speed={1} {...props} />);
    expect(screen.getByRole('button', { name: 'Next candle' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous candle' })).toBeDisabled();
  });

  it('enables Next/Previous/Stop/Restart while paused', () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={1} {...props} />);
    expect(screen.getByRole('button', { name: 'Next candle' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Previous candle' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Restart' })).toBeEnabled();
  });

  it('calls onNext/onPrevious/onStop/onRestart', () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={1} {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Next candle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Previous candle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    fireEvent.click(screen.getByRole('button', { name: 'Restart' }));
    expect(props.onNext).toHaveBeenCalledTimes(1);
    expect(props.onPrevious).toHaveBeenCalledTimes(1);
    expect(props.onStop).toHaveBeenCalledTimes(1);
    expect(props.onRestart).toHaveBeenCalledTimes(1);
  });

  it('renders every required speed option and marks the current one selected', () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={2} {...props} />);
    for (const label of [
      '0.25x speed',
      '0.5x speed',
      '1x speed',
      '2x speed',
      '5x speed',
      '10x speed',
    ]) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: '2x speed' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('calls onSpeedChange with the selected speed', () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={1} {...props} />);
    fireEvent.click(screen.getByRole('button', { name: '10x speed' }));
    expect(props.onSpeedChange).toHaveBeenCalledWith(10);
  });

  it('does not call onSpeedChange when clicking the already-selected speed', () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={1} {...props} />);
    fireEvent.click(screen.getByRole('button', { name: '1x speed' }));
    expect(props.onSpeedChange).not.toHaveBeenCalled();
  });

  it('still marks the correct speed selected when each button is wrapped in its own tooltip', () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={5} {...props} />);
    expect(screen.getByRole('button', { name: '5x speed' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: '1x speed' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('shows a tooltip explaining a speed button on hover, despite the ToggleButtonGroup wrapping', async () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={1} {...props} />);
    fireEvent.mouseOver(screen.getByRole('button', { name: '2x speed' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Play at 2× speed');
  });

  it('names the keyboard shortcut in the Play/Pause/Next/Previous tooltips', async () => {
    const props = handlers();
    render(<ReplayControls phase="paused" speed={1} {...props} />);
    fireEvent.mouseOver(screen.getByRole('button', { name: 'Resume' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Space');
  });
});
