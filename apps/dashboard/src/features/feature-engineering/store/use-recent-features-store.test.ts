import { act } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useRecentFeaturesStore } from './use-recent-features-store';

afterEach(() => {
  act(() => useRecentFeaturesStore.getState().clear());
  sessionStorage.clear();
});

describe('useRecentFeaturesStore', () => {
  it('records a used feature at the front of the list', () => {
    act(() => useRecentFeaturesStore.getState().recordUsed('sma'));
    expect(useRecentFeaturesStore.getState().recent).toEqual(['sma']);
  });

  it('moves a re-used feature back to the front rather than duplicating it', () => {
    act(() => {
      useRecentFeaturesStore.getState().recordUsed('sma');
      useRecentFeaturesStore.getState().recordUsed('ema');
      useRecentFeaturesStore.getState().recordUsed('sma');
    });
    expect(useRecentFeaturesStore.getState().recent).toEqual(['sma', 'ema']);
  });

  it('caps the list at the maximum, dropping the oldest', () => {
    act(() => {
      for (let i = 0; i < 10; i += 1) {
        useRecentFeaturesStore.getState().recordUsed(`feature-${i}`);
      }
    });
    const recent = useRecentFeaturesStore.getState().recent;
    expect(recent).toHaveLength(8);
    expect(recent[0]).toBe('feature-9'); // most recent first
    expect(recent).not.toContain('feature-0'); // oldest dropped
  });

  it('clears the list', () => {
    act(() => {
      useRecentFeaturesStore.getState().recordUsed('sma');
      useRecentFeaturesStore.getState().clear();
    });
    expect(useRecentFeaturesStore.getState().recent).toEqual([]);
  });
});
