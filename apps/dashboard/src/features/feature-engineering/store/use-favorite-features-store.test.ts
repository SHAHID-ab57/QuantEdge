import { act } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useFavoriteFeaturesStore } from './use-favorite-features-store';

afterEach(() => {
  act(() => useFavoriteFeaturesStore.getState().clear());
  localStorage.clear();
});

describe('useFavoriteFeaturesStore', () => {
  it('adds a feature to favorites on first toggle', () => {
    act(() => useFavoriteFeaturesStore.getState().toggle('sma'));
    expect(useFavoriteFeaturesStore.getState().favorites).toEqual(['sma']);
  });

  it('removes a feature from favorites on a second toggle', () => {
    act(() => {
      useFavoriteFeaturesStore.getState().toggle('sma');
      useFavoriteFeaturesStore.getState().toggle('sma');
    });
    expect(useFavoriteFeaturesStore.getState().favorites).toEqual([]);
  });

  it('reports whether a feature is currently favorited', () => {
    expect(useFavoriteFeaturesStore.getState().isFavorite('sma')).toBe(false);
    act(() => useFavoriteFeaturesStore.getState().toggle('sma'));
    expect(useFavoriteFeaturesStore.getState().isFavorite('sma')).toBe(true);
  });

  it('supports multiple independent favorites', () => {
    act(() => {
      useFavoriteFeaturesStore.getState().toggle('sma');
      useFavoriteFeaturesStore.getState().toggle('ema');
    });
    expect(useFavoriteFeaturesStore.getState().favorites.sort()).toEqual(['ema', 'sma']);
  });

  it('clears every favorite', () => {
    act(() => {
      useFavoriteFeaturesStore.getState().toggle('sma');
      useFavoriteFeaturesStore.getState().clear();
    });
    expect(useFavoriteFeaturesStore.getState().favorites).toEqual([]);
  });
});
