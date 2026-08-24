'use client';

import { useEffect } from 'react';
import { fasterSpeed, slowerSpeed, type ReplaySpeed } from '../engine/replay-speed';
import type { ReplayPhase } from '../engine/replay-state-machine';

export interface UseReplayKeyboardShortcutsOptions {
  enabled: boolean;
  phase: ReplayPhase;
  speed: ReplaySpeed;
  candleCount: number;
  play: () => void;
  resume: () => void;
  pause: () => void;
  next: () => void;
  previous: () => void;
  seekToIndex: (index: number) => void;
  setSpeed: (speed: ReplaySpeed) => void;
}

const TYPING_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

/**
 * Skips the shortcut when focus is somewhere that should keep its own key
 * handling — a text field (including the config form's date/time inputs),
 * a contentEditable region, or the timeline `Slider`'s thumb, which MUI
 * already makes independently arrow-key-adjustable. Without this, Space
 * would toggle playback while a researcher is typing a date, and the
 * global Left/Right handlers would fight the focused slider's own.
 */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    TYPING_TAGS.has(target.tagName) ||
    target.isContentEditable ||
    target.closest('[role="slider"]') !== null
  );
}

/**
 * Global keyboard shortcuts for replay playback — Space (play/pause),
 * ArrowRight/ArrowLeft (next/previous candle), Home/End (jump to the first/
 * last loaded candle), and `+`/`-` (speed up/down through `REPLAY_SPEEDS`).
 * Attached to `window` rather than a specific element so a shortcut works
 * regardless of which part of the page currently has focus, matching how
 * a media player's shortcuts are typically global to the page.
 *
 * `enabled` gates the whole hook (no listener at all, not just a no-op
 * handler) so shortcuts do nothing before a session is loaded — `false`
 * while `phase` is `idle`/`loading`/`error`, mirroring the same phases
 * `ReplayControls` already disables its buttons for.
 */
export function useReplayKeyboardShortcuts({
  enabled,
  phase,
  speed,
  candleCount,
  play,
  resume,
  pause,
  next,
  previous,
  seekToIndex,
  setSpeed,
}: UseReplayKeyboardShortcutsOptions): void {
  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }

      switch (event.key) {
        case ' ':
        case 'Spacebar':
          event.preventDefault();
          if (phase === 'playing') {
            pause();
          } else if (phase === 'paused' || phase === 'completed') {
            (phase === 'paused' ? resume : play)();
          }
          return;
        case 'ArrowRight':
          event.preventDefault();
          next();
          return;
        case 'ArrowLeft':
          event.preventDefault();
          previous();
          return;
        case 'Home':
          event.preventDefault();
          seekToIndex(0);
          return;
        case 'End':
          event.preventDefault();
          seekToIndex(candleCount - 1);
          return;
        case '+':
        case '=':
          event.preventDefault();
          setSpeed(fasterSpeed(speed));
          return;
        case '-':
        case '_':
          event.preventDefault();
          setSpeed(slowerSpeed(speed));
          return;
        default:
          return;
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    enabled,
    phase,
    speed,
    candleCount,
    play,
    resume,
    pause,
    next,
    previous,
    seekToIndex,
    setSpeed,
  ]);
}
