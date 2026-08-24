import { describe, expect, it } from 'vitest';
import { createInitialReplayState, replayReducer, type ReplayState } from './replay-state-machine';

function loaded(overrides: Partial<ReplayState> = {}): ReplayState {
  return {
    ...createInitialReplayState(),
    phase: 'paused',
    candleCount: 5,
    currentIndex: 0,
    revealEpoch: 1,
    ...overrides,
  };
}

describe('createInitialReplayState', () => {
  it('starts idle, at index 0, at the default speed, with no error', () => {
    const state = createInitialReplayState();
    expect(state.phase).toBe('idle');
    expect(state.currentIndex).toBe(0);
    expect(state.candleCount).toBe(0);
    expect(state.speed).toBe(1);
    expect(state.error).toBeNull();
  });
});

describe('LOAD_START / LOAD_SUCCESS / LOAD_ERROR', () => {
  it('moves to loading and resets any prior session', () => {
    const state = replayReducer(loaded({ currentIndex: 3 }), { type: 'LOAD_START' });
    expect(state.phase).toBe('loading');
    expect(state.currentIndex).toBe(0);
    expect(state.candleCount).toBe(0);
  });

  it('preserves the previously-selected speed across a reload', () => {
    const withSpeed = replayReducer(loaded({ speed: 5 }), { type: 'LOAD_START' });
    expect(withSpeed.speed).toBe(5);
  });

  it('moves to paused with the loaded candle count on success', () => {
    const loading = replayReducer(createInitialReplayState(), { type: 'LOAD_START' });
    const state = replayReducer(loading, { type: 'LOAD_SUCCESS', candleCount: 200 });
    expect(state.phase).toBe('paused');
    expect(state.candleCount).toBe(200);
    expect(state.error).toBeNull();
  });

  it('moves to error when the load succeeds with zero candles (empty replay)', () => {
    const loading = replayReducer(createInitialReplayState(), { type: 'LOAD_START' });
    const state = replayReducer(loading, { type: 'LOAD_SUCCESS', candleCount: 0 });
    expect(state.phase).toBe('error');
    expect(state.error).toMatch(/no candles/i);
  });

  it('moves to error with the given message on a failed load', () => {
    const loading = replayReducer(createInitialReplayState(), { type: 'LOAD_START' });
    const state = replayReducer(loading, { type: 'LOAD_ERROR', message: 'Backend unavailable' });
    expect(state.phase).toBe('error');
    expect(state.error).toBe('Backend unavailable');
  });

  it('ignores a stray LOAD_SUCCESS/LOAD_ERROR that arrives outside the loading phase', () => {
    const idle = createInitialReplayState();
    expect(replayReducer(idle, { type: 'LOAD_SUCCESS', candleCount: 10 })).toBe(idle);
    expect(replayReducer(idle, { type: 'LOAD_ERROR', message: 'late' })).toBe(idle);
  });
});

describe('PLAY', () => {
  it('starts playing from paused without touching the current index', () => {
    const state = replayReducer(loaded({ currentIndex: 2 }), { type: 'PLAY' });
    expect(state.phase).toBe('playing');
    expect(state.currentIndex).toBe(2);
  });

  it('restarts from index 0 when played again after completion', () => {
    const completed = loaded({ phase: 'completed', currentIndex: 4 });
    const state = replayReducer(completed, { type: 'PLAY' });
    expect(state.phase).toBe('playing');
    expect(state.currentIndex).toBe(0);
  });

  it('is a no-op from idle, loading, error, or already-playing', () => {
    for (const phase of ['idle', 'loading', 'error', 'playing'] as const) {
      const state = loaded({ phase });
      expect(replayReducer(state, { type: 'PLAY' })).toBe(state);
    }
  });
});

describe('RESUME', () => {
  it('resumes from paused at the same index', () => {
    const state = replayReducer(loaded({ currentIndex: 3 }), { type: 'RESUME' });
    expect(state.phase).toBe('playing');
    expect(state.currentIndex).toBe(3);
  });

  it('is invalid from every phase except paused', () => {
    for (const phase of ['idle', 'loading', 'playing', 'completed', 'error', 'seeking'] as const) {
      const state = loaded({ phase });
      expect(replayReducer(state, { type: 'RESUME' })).toBe(state);
    }
  });
});

describe('PAUSE', () => {
  it('pauses while playing', () => {
    const state = replayReducer(loaded({ phase: 'playing' }), { type: 'PAUSE' });
    expect(state.phase).toBe('paused');
  });

  it('is a no-op outside playing', () => {
    const state = loaded({ phase: 'paused' });
    expect(replayReducer(state, { type: 'PAUSE' })).toBe(state);
  });
});

describe('STOP', () => {
  it('resets to index 0 and pauses from playing', () => {
    const state = replayReducer(loaded({ phase: 'playing', currentIndex: 4 }), { type: 'STOP' });
    expect(state.phase).toBe('paused');
    expect(state.currentIndex).toBe(0);
  });

  it('resets to index 0 and pauses from completed', () => {
    const state = replayReducer(loaded({ phase: 'completed', currentIndex: 4 }), { type: 'STOP' });
    expect(state.phase).toBe('paused');
    expect(state.currentIndex).toBe(0);
  });

  it('bumps revealEpoch, since resetting to 0 is a discontinuous jump', () => {
    const before = loaded({ phase: 'playing', currentIndex: 4, revealEpoch: 2 });
    expect(replayReducer(before, { type: 'STOP' }).revealEpoch).toBe(3);
  });

  it('is a no-op from idle/loading/error', () => {
    for (const phase of ['idle', 'loading', 'error'] as const) {
      const state = loaded({ phase });
      expect(replayReducer(state, { type: 'STOP' })).toBe(state);
    }
  });
});

describe('RESTART', () => {
  it('resets to index 0 while preserving the playing phase', () => {
    const state = replayReducer(loaded({ phase: 'playing', currentIndex: 4 }), {
      type: 'RESTART',
    });
    expect(state.phase).toBe('playing');
    expect(state.currentIndex).toBe(0);
  });

  it('resets to index 0 while preserving the paused phase', () => {
    const state = replayReducer(loaded({ phase: 'paused', currentIndex: 4 }), { type: 'RESTART' });
    expect(state.phase).toBe('paused');
    expect(state.currentIndex).toBe(0);
  });

  it('moves completed back to paused at index 0', () => {
    const state = replayReducer(loaded({ phase: 'completed', currentIndex: 4 }), {
      type: 'RESTART',
    });
    expect(state.phase).toBe('paused');
    expect(state.currentIndex).toBe(0);
  });

  it('is a no-op from idle/loading/error', () => {
    for (const phase of ['idle', 'loading', 'error'] as const) {
      const state = loaded({ phase });
      expect(replayReducer(state, { type: 'RESTART' })).toBe(state);
    }
  });
});

describe('NEXT', () => {
  it('advances the index by one', () => {
    const state = replayReducer(loaded({ currentIndex: 1 }), { type: 'NEXT' });
    expect(state.currentIndex).toBe(2);
    expect(state.phase).toBe('paused');
  });

  it('transitions to completed on reaching the last candle', () => {
    const state = replayReducer(loaded({ currentIndex: 3, candleCount: 5 }), { type: 'NEXT' });
    expect(state.currentIndex).toBe(4);
    expect(state.phase).toBe('completed');
  });

  it('is a no-op once already completed at the last index', () => {
    const state = loaded({ phase: 'completed', currentIndex: 4, candleCount: 5 });
    const next = replayReducer(state, { type: 'NEXT' });
    expect(next.currentIndex).toBe(4);
    expect(next.phase).toBe('completed');
  });

  it('is valid while playing too (a manual step alongside auto-advance)', () => {
    const state = replayReducer(loaded({ phase: 'playing', currentIndex: 1 }), { type: 'NEXT' });
    expect(state.currentIndex).toBe(2);
    expect(state.phase).toBe('playing');
  });

  it('is a no-op from idle/loading/error/seeking', () => {
    for (const phase of ['idle', 'loading', 'error', 'seeking'] as const) {
      const state = loaded({ phase });
      expect(replayReducer(state, { type: 'NEXT' })).toBe(state);
    }
  });
});

describe('TICK', () => {
  it('behaves like NEXT while playing', () => {
    const state = replayReducer(loaded({ phase: 'playing', currentIndex: 1 }), { type: 'TICK' });
    expect(state.currentIndex).toBe(2);
  });

  it('is a no-op outside playing — a stray scheduler tick after pause must not advance', () => {
    const state = loaded({ phase: 'paused', currentIndex: 1 });
    expect(replayReducer(state, { type: 'TICK' })).toBe(state);
  });

  it('completes replay on reaching the last candle', () => {
    const state = replayReducer(loaded({ phase: 'playing', currentIndex: 3, candleCount: 5 }), {
      type: 'TICK',
    });
    expect(state.phase).toBe('completed');
    expect(state.currentIndex).toBe(4);
  });
});

describe('PREVIOUS', () => {
  it('steps the index back by one', () => {
    const state = replayReducer(loaded({ currentIndex: 3 }), { type: 'PREVIOUS' });
    expect(state.currentIndex).toBe(2);
    expect(state.phase).toBe('paused');
  });

  it('moves completed back to paused', () => {
    const state = replayReducer(loaded({ phase: 'completed', currentIndex: 4 }), {
      type: 'PREVIOUS',
    });
    expect(state.phase).toBe('paused');
    expect(state.currentIndex).toBe(3);
  });

  it('is a no-op at index 0', () => {
    const state = loaded({ currentIndex: 0 });
    expect(replayReducer(state, { type: 'PREVIOUS' })).toBe(state);
  });

  it('bumps revealEpoch — stepping backward is a discontinuous jump for the chart', () => {
    const before = loaded({ currentIndex: 3, revealEpoch: 1 });
    expect(replayReducer(before, { type: 'PREVIOUS' }).revealEpoch).toBe(2);
  });

  it('is a no-op while playing (manual rewind pauses first)', () => {
    const state = loaded({ phase: 'playing', currentIndex: 2 });
    expect(replayReducer(state, { type: 'PREVIOUS' })).toBe(state);
  });
});

describe('seeking (SEEK_START then SEEK_COMPLETE)', () => {
  it('passes through the seeking phase', () => {
    const seeking = replayReducer(loaded(), { type: 'SEEK_START' });
    expect(seeking.phase).toBe('seeking');
  });

  it('resolves to paused at the target index when not resuming to playing', () => {
    const seeking = replayReducer(loaded(), { type: 'SEEK_START' });
    const state = replayReducer(seeking, {
      type: 'SEEK_COMPLETE',
      index: 3,
      resumeToPlaying: false,
    });
    expect(state.phase).toBe('paused');
    expect(state.currentIndex).toBe(3);
  });

  it('resolves back to playing when the seek started mid-playback', () => {
    const seeking = replayReducer(loaded({ phase: 'playing' }), { type: 'SEEK_START' });
    const state = replayReducer(seeking, {
      type: 'SEEK_COMPLETE',
      index: 3,
      resumeToPlaying: true,
    });
    expect(state.phase).toBe('playing');
    expect(state.currentIndex).toBe(3);
  });

  it('clamps a seek target beyond the loaded range', () => {
    const seeking = replayReducer(loaded(), { type: 'SEEK_START' });
    const state = replayReducer(seeking, {
      type: 'SEEK_COMPLETE',
      index: 999,
      resumeToPlaying: false,
    });
    expect(state.currentIndex).toBe(4); // candleCount - 1
  });

  it('bumps revealEpoch on completion', () => {
    const seeking = replayReducer(loaded({ revealEpoch: 1 }), { type: 'SEEK_START' });
    const state = replayReducer(seeking, {
      type: 'SEEK_COMPLETE',
      index: 1,
      resumeToPlaying: false,
    });
    expect(state.revealEpoch).toBe(2);
  });

  it('completes replay when a seek lands exactly on the last candle', () => {
    const seeking = replayReducer(loaded(), { type: 'SEEK_START' });
    const state = replayReducer(seeking, {
      type: 'SEEK_COMPLETE',
      index: 4,
      resumeToPlaying: false,
    });
    expect(state.phase).toBe('completed');
    expect(state.currentIndex).toBe(4);
  });

  it('completes replay when a seek clamps to the last candle, even if it asked to resume playing', () => {
    const seeking = replayReducer(loaded({ phase: 'playing' }), { type: 'SEEK_START' });
    const state = replayReducer(seeking, {
      type: 'SEEK_COMPLETE',
      index: 999,
      resumeToPlaying: true,
    });
    expect(state.phase).toBe('completed');
  });

  it('refuses to start a seek with nothing loaded', () => {
    const idle = createInitialReplayState();
    expect(replayReducer(idle, { type: 'SEEK_START' })).toBe(idle);
  });

  it('ignores a stray SEEK_COMPLETE outside the seeking phase', () => {
    const state = loaded();
    expect(replayReducer(state, { type: 'SEEK_COMPLETE', index: 1, resumeToPlaying: false })).toBe(
      state,
    );
  });
});

describe('SET_SPEED', () => {
  it('updates speed without touching phase or index', () => {
    const state = replayReducer(loaded({ phase: 'playing', currentIndex: 2, speed: 1 }), {
      type: 'SET_SPEED',
      speed: 10,
    });
    expect(state.speed).toBe(10);
    expect(state.phase).toBe('playing');
    expect(state.currentIndex).toBe(2);
  });

  it('does not bump revealEpoch — changing speed must not restart replay', () => {
    const before = loaded({ revealEpoch: 5 });
    expect(replayReducer(before, { type: 'SET_SPEED', speed: 2 }).revealEpoch).toBe(5);
  });

  it('is valid regardless of phase', () => {
    for (const phase of ['idle', 'loading', 'error', 'completed'] as const) {
      const state = replayReducer(loaded({ phase }), { type: 'SET_SPEED', speed: 0.25 });
      expect(state.speed).toBe(0.25);
    }
  });
});
