import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useReplayKeyboardShortcuts } from './use-replay-keyboard-shortcuts';

function handlers() {
  return {
    play: vi.fn(),
    resume: vi.fn(),
    pause: vi.fn(),
    next: vi.fn(),
    previous: vi.fn(),
    seekToIndex: vi.fn(),
    setSpeed: vi.fn(),
  };
}

function fireKey(key: string, target: EventTarget = window) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  return event;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useReplayKeyboardShortcuts', () => {
  it('toggles pause when Space is pressed while playing', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'playing',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    fireKey(' ');
    expect(props.pause).toHaveBeenCalledTimes(1);
    expect(props.play).not.toHaveBeenCalled();
    expect(props.resume).not.toHaveBeenCalled();
  });

  it('resumes (not restarts) when Space is pressed while paused', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'paused',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    fireKey(' ');
    expect(props.resume).toHaveBeenCalledTimes(1);
    expect(props.play).not.toHaveBeenCalled();
  });

  it('plays (restarting from zero) when Space is pressed after completion', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'completed',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    fireKey(' ');
    expect(props.play).toHaveBeenCalledTimes(1);
    expect(props.resume).not.toHaveBeenCalled();
  });

  it('steps forward/backward on ArrowRight/ArrowLeft', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'paused',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    fireKey('ArrowRight');
    fireKey('ArrowLeft');
    expect(props.next).toHaveBeenCalledTimes(1);
    expect(props.previous).toHaveBeenCalledTimes(1);
  });

  it('jumps to the first and last candle on Home/End', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'paused',
        speed: 1,
        candleCount: 250,
        ...props,
      }),
    );
    fireKey('Home');
    fireKey('End');
    expect(props.seekToIndex).toHaveBeenNthCalledWith(1, 0);
    expect(props.seekToIndex).toHaveBeenNthCalledWith(2, 249);
  });

  it('increases and decreases speed on +/-', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'paused',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    fireKey('+');
    fireKey('-');
    expect(props.setSpeed).toHaveBeenNthCalledWith(1, 2);
    expect(props.setSpeed).toHaveBeenNthCalledWith(2, 0.5);
  });

  it('does nothing when disabled — no listener at all', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: false,
        phase: 'paused',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    fireKey(' ');
    fireKey('ArrowRight');
    expect(props.resume).not.toHaveBeenCalled();
    expect(props.next).not.toHaveBeenCalled();
  });

  it('ignores shortcuts while typing in a text field', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'paused',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    fireKey('ArrowRight', input);
    expect(props.next).not.toHaveBeenCalled();
  });

  it('ignores shortcuts within a focused slider, letting it handle its own arrow keys', () => {
    const slider = document.createElement('div');
    slider.setAttribute('role', 'slider');
    const thumb = document.createElement('div');
    slider.appendChild(thumb);
    document.body.appendChild(slider);
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'paused',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    fireKey('ArrowRight', thumb);
    expect(props.next).not.toHaveBeenCalled();
  });

  it('ignores the shortcut when a modifier key is held (e.g. Cmd+Space for a launcher)', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'playing',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    const event = new KeyboardEvent('keydown', { key: ' ', metaKey: true, cancelable: true });
    window.dispatchEvent(event);
    expect(props.pause).not.toHaveBeenCalled();
  });

  it('removes its listener on unmount', () => {
    const props = handlers();
    const { unmount } = renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'playing',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    unmount();
    fireKey(' ');
    expect(props.pause).not.toHaveBeenCalled();
  });

  it('prevents the default action for a handled key (stops the page from scrolling)', () => {
    const props = handlers();
    renderHook(() =>
      useReplayKeyboardShortcuts({
        enabled: true,
        phase: 'paused',
        speed: 1,
        candleCount: 10,
        ...props,
      }),
    );
    const event = fireKey('ArrowRight');
    expect(event.defaultPrevented).toBe(true);
  });
});
