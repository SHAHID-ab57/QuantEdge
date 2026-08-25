import { act } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useRecentColumnsStore } from './use-recent-columns-store';

afterEach(() => {
  act(() => useRecentColumnsStore.getState().clear());
  sessionStorage.clear();
});

describe('useRecentColumnsStore', () => {
  it('records a used column at the front of the list', () => {
    act(() => useRecentColumnsStore.getState().recordUsed('close'));
    expect(useRecentColumnsStore.getState().recent).toEqual(['close']);
  });

  it('moves a re-used column back to the front rather than duplicating it', () => {
    act(() => {
      useRecentColumnsStore.getState().recordUsed('close');
      useRecentColumnsStore.getState().recordUsed('sma_20');
      useRecentColumnsStore.getState().recordUsed('close');
    });
    expect(useRecentColumnsStore.getState().recent).toEqual(['close', 'sma_20']);
  });

  it('caps the list at the maximum, dropping the oldest', () => {
    act(() => {
      for (let i = 0; i < 10; i += 1) {
        useRecentColumnsStore.getState().recordUsed(`column-${i}`);
      }
    });
    const recent = useRecentColumnsStore.getState().recent;
    expect(recent).toHaveLength(8);
    expect(recent[0]).toBe('column-9');
    expect(recent).not.toContain('column-0');
  });

  it('clears the list', () => {
    act(() => {
      useRecentColumnsStore.getState().recordUsed('close');
      useRecentColumnsStore.getState().clear();
    });
    expect(useRecentColumnsStore.getState().recent).toEqual([]);
  });
});
