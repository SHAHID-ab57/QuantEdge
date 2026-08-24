import { act } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { Indicator } from '@/types/api/indicators';
import { useOverlayStore } from './use-overlay-store';

function indicator(overrides: Partial<Indicator> = {}): Indicator {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'Stub.',
    category: 'trend',
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period parameter.',
    parameters: [
      {
        name: 'period',
        type: 'int',
        label: 'Period',
        description: 'Window size.',
        default: 20,
        required: false,
        minimum: 1,
        maximum: 1000,
        choices: [],
      },
    ],
    outputs: [{ name: 'sma', label: 'SMA', description: '' }],
    ...overrides,
  };
}

afterEach(() => {
  act(() => useOverlayStore.getState().clearOverlays());
  sessionStorage.clear();
});

describe('useOverlayStore — addOverlay', () => {
  it('adds an overlay seeded with the indicator’s published defaults', () => {
    act(() => useOverlayStore.getState().addOverlay(indicator()));
    const [overlay] = useOverlayStore.getState().overlays;
    expect(overlay).toMatchObject({
      indicator: 'sma',
      label: 'Simple Moving Average',
      params: { period: '20' },
      enabled: true,
    });
  });

  it('gives each added overlay a unique id', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator());
      useOverlayStore.getState().addOverlay(indicator());
    });
    const [first, second] = useOverlayStore.getState().overlays;
    expect(first!.id).not.toBe(second!.id);
  });

  it('assigns increasing, stable color indices', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator({ name: 'sma' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'ema' }));
    });
    const [first, second] = useOverlayStore.getState().overlays;
    expect(first!.colorIndex).toBe(0);
    expect(second!.colorIndex).toBe(1);
  });

  it('does not reassign a remaining overlay’s color index when an earlier one is removed', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator({ name: 'sma' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'ema' }));
    });
    const [first, second] = useOverlayStore.getState().overlays;
    act(() => useOverlayStore.getState().removeOverlay(first!.id));
    const remaining = useOverlayStore.getState().overlays[0]!;
    expect(remaining.id).toBe(second!.id);
    expect(remaining.colorIndex).toBe(1); // unchanged, not renumbered to 0
  });

  it('allows adding the same indicator twice as distinct overlays', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator());
      useOverlayStore.getState().addOverlay(indicator());
    });
    expect(useOverlayStore.getState().overlays).toHaveLength(2);
  });
});

describe('useOverlayStore — removeOverlay', () => {
  it('removes only the targeted overlay', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator({ name: 'sma' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'ema' }));
    });
    const [first] = useOverlayStore.getState().overlays;
    act(() => useOverlayStore.getState().removeOverlay(first!.id));
    const remaining = useOverlayStore.getState().overlays;
    expect(remaining).toHaveLength(1);
    expect(remaining[0]!.indicator).toBe('ema');
  });

  it('is a no-op for an unknown id', () => {
    act(() => useOverlayStore.getState().addOverlay(indicator()));
    act(() => useOverlayStore.getState().removeOverlay('nope'));
    expect(useOverlayStore.getState().overlays).toHaveLength(1);
  });
});

describe('useOverlayStore — toggleOverlay', () => {
  it('flips enabled on and back off', () => {
    act(() => useOverlayStore.getState().addOverlay(indicator()));
    const id = useOverlayStore.getState().overlays[0]!.id;

    act(() => useOverlayStore.getState().toggleOverlay(id));
    expect(useOverlayStore.getState().overlays[0]!.enabled).toBe(false);

    act(() => useOverlayStore.getState().toggleOverlay(id));
    expect(useOverlayStore.getState().overlays[0]!.enabled).toBe(true);
  });

  it('does not affect other overlays', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator({ name: 'sma' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'ema' }));
    });
    const [first, second] = useOverlayStore.getState().overlays;
    act(() => useOverlayStore.getState().toggleOverlay(first!.id));
    expect(useOverlayStore.getState().overlays.find((o) => o.id === second!.id)!.enabled).toBe(
      true,
    );
  });
});

describe('useOverlayStore — updateOverlayParams', () => {
  it('replaces the params of the targeted overlay', () => {
    act(() => useOverlayStore.getState().addOverlay(indicator()));
    const id = useOverlayStore.getState().overlays[0]!.id;
    act(() => useOverlayStore.getState().updateOverlayParams(id, { period: '50' }));
    expect(useOverlayStore.getState().overlays[0]!.params).toEqual({ period: '50' });
  });
});

describe('useOverlayStore — setOverlayColor', () => {
  it('sets a manual override for the targeted overlay', () => {
    act(() => useOverlayStore.getState().addOverlay(indicator()));
    const id = useOverlayStore.getState().overlays[0]!.id;
    act(() => useOverlayStore.getState().setOverlayColor(id, '#ff00ff'));
    expect(useOverlayStore.getState().overlays[0]!.colorOverride).toBe('#ff00ff');
  });

  it('resets to automatic when passed null', () => {
    act(() => useOverlayStore.getState().addOverlay(indicator()));
    const id = useOverlayStore.getState().overlays[0]!.id;
    act(() => useOverlayStore.getState().setOverlayColor(id, '#ff00ff'));
    act(() => useOverlayStore.getState().setOverlayColor(id, null));
    expect(useOverlayStore.getState().overlays[0]!.colorOverride).toBeNull();
  });

  it('does not affect other overlays', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator({ name: 'sma' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'ema' }));
    });
    const [first, second] = useOverlayStore.getState().overlays;
    act(() => useOverlayStore.getState().setOverlayColor(first!.id, '#ff00ff'));
    expect(
      useOverlayStore.getState().overlays.find((o) => o.id === second!.id)!.colorOverride,
    ).toBeUndefined();
  });
});

describe('useOverlayStore — moveOverlayToIndex', () => {
  it('moves an overlay later in the list', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator({ name: 'sma' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'ema' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'wma' }));
    });
    const [first] = useOverlayStore.getState().overlays;
    act(() => useOverlayStore.getState().moveOverlayToIndex(first!.id, 2));
    expect(useOverlayStore.getState().overlays.map((o) => o.indicator)).toEqual([
      'ema',
      'wma',
      'sma',
    ]);
  });

  it('moves an overlay earlier in the list', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator({ name: 'sma' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'ema' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'wma' }));
    });
    const last = useOverlayStore.getState().overlays[2]!;
    act(() => useOverlayStore.getState().moveOverlayToIndex(last.id, 0));
    expect(useOverlayStore.getState().overlays.map((o) => o.indicator)).toEqual([
      'wma',
      'sma',
      'ema',
    ]);
  });

  it('is a no-op for an unknown id', () => {
    act(() => useOverlayStore.getState().addOverlay(indicator()));
    const before = useOverlayStore.getState().overlays;
    act(() => useOverlayStore.getState().moveOverlayToIndex('nope', 0));
    expect(useOverlayStore.getState().overlays).toBe(before);
  });

  it('clamps an out-of-range target index instead of throwing', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator({ name: 'sma' }));
      useOverlayStore.getState().addOverlay(indicator({ name: 'ema' }));
    });
    const [first] = useOverlayStore.getState().overlays;
    act(() => useOverlayStore.getState().moveOverlayToIndex(first!.id, 99));
    expect(useOverlayStore.getState().overlays.map((o) => o.indicator)).toEqual(['ema', 'sma']);
  });
});

describe('useOverlayStore — clearOverlays', () => {
  it('empties the overlay list and resets the color counter', () => {
    act(() => {
      useOverlayStore.getState().addOverlay(indicator());
      useOverlayStore.getState().clearOverlays();
      useOverlayStore.getState().addOverlay(indicator());
    });
    expect(useOverlayStore.getState().overlays).toHaveLength(1);
    expect(useOverlayStore.getState().overlays[0]!.colorIndex).toBe(0);
  });
});
