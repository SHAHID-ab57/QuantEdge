'use client';

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { defaultValuesFor } from '@/features/indicators/lib/parameter-values';
import type { Indicator } from '@/types/api/indicators';

/**
 * One indicator added to the chart as an overlay. Distinct from a
 * calculation *result* — this is pure configuration (which indicator,
 * which parameters, on or off), independent of whatever the backend last
 * computed for it.
 */
export interface OverlayConfig {
  /** Unique per overlay *instance* — a researcher can add the same indicator twice with different periods. */
  id: string;
  indicator: string;
  label: string;
  params: Record<string, string>;
  enabled: boolean;
  /**
   * A stable index into the shared overlay color rotation
   * (`@/components/chart/overlay-colors`), assigned once at creation and
   * never reassigned — removing one overlay must not shift every other
   * overlay's color, which would make the chart's legend and lines
   * momentarily disagree with what a researcher just memorized.
   */
  colorIndex: number;
  /**
   * A manual color override, taking precedence over `colorIndex`'s
   * automatic rotation when set — see `resolveOverlayColor`
   * (`@/components/chart/overlay-colors`). `undefined`/`null` means "use
   * the automatic color"; optional so overlays persisted before this field
   * existed still deserialize correctly (they simply have no override).
   */
  colorOverride?: string | null;
}

interface OverlayState {
  overlays: OverlayConfig[];
  /** Monotonically increasing — the source of each new overlay's stable `colorIndex`. */
  nextColorIndex: number;
  addOverlay: (indicator: Indicator) => string;
  removeOverlay: (id: string) => void;
  toggleOverlay: (id: string) => void;
  updateOverlayParams: (id: string, params: Record<string, string>) => void;
  /** `color`: a CSS color to override the automatic rotation with; `null` resets to automatic. */
  setOverlayColor: (id: string, color: string | null) => void;
  /**
   * Moves one overlay to a new position in the list — the store-side half
   * of the Indicator Legend's drag-and-drop reordering. Render order (both
   * the legend's list order and the chart's line z-order) follows this
   * array's order directly, so reordering here is reordering everywhere.
   */
  moveOverlayToIndex: (id: string, toIndex: number) => void;
  clearOverlays: () => void;
}

let idCounter = 0;

/** A short, collision-free-enough id for one browser session's overlay list. */
function nextOverlayId(): string {
  idCounter += 1;
  return `overlay-${Date.now().toString(36)}-${idCounter}`;
}

/**
 * Session-scoped indicator overlay configuration — which indicators are on
 * the chart, their parameters, and whether each is currently visible.
 *
 * This is UI/session configuration, not server data (that's TanStack
 * Query's job) and not app chrome (that's `ui-store.ts`'s job) — a new,
 * dedicated store keeps those responsibilities apart. Persisted to
 * `sessionStorage` (not `localStorage`): the task asks for "the current
 * session," and `sessionStorage` is the browser primitive that means
 * exactly that — it survives a reload but clears when the tab closes,
 * unlike `localStorage`, which would silently outlive "this session."
 *
 * Deliberately shaped as a flat, plain-JSON-serializable list: a future
 * "saved workspace" feature is a persistence-backend swap (write this same
 * shape to a backend endpoint instead of `sessionStorage`, load it back
 * into this same store on open) rather than a redesign of the state or
 * the components that read it.
 */
export const useOverlayStore = create<OverlayState>()(
  persist(
    (set, get) => ({
      overlays: [],
      nextColorIndex: 0,

      addOverlay: (indicator) => {
        const id = nextOverlayId();
        const params = defaultValuesFor(indicator.parameters);
        const colorIndex = get().nextColorIndex;
        set((state) => ({
          overlays: [
            ...state.overlays,
            {
              id,
              indicator: indicator.name,
              label: indicator.label,
              params,
              enabled: true,
              colorIndex,
            },
          ],
          nextColorIndex: colorIndex + 1,
        }));
        return id;
      },

      removeOverlay: (id) => {
        set((state) => ({ overlays: state.overlays.filter((overlay) => overlay.id !== id) }));
      },

      toggleOverlay: (id) => {
        set((state) => ({
          overlays: state.overlays.map((overlay) =>
            overlay.id === id ? { ...overlay, enabled: !overlay.enabled } : overlay,
          ),
        }));
      },

      updateOverlayParams: (id, params) => {
        set((state) => ({
          overlays: state.overlays.map((overlay) =>
            overlay.id === id ? { ...overlay, params } : overlay,
          ),
        }));
      },

      setOverlayColor: (id, color) => {
        set((state) => ({
          overlays: state.overlays.map((overlay) =>
            overlay.id === id ? { ...overlay, colorOverride: color } : overlay,
          ),
        }));
      },

      moveOverlayToIndex: (id, toIndex) => {
        set((state) => {
          const fromIndex = state.overlays.findIndex((overlay) => overlay.id === id);
          if (fromIndex === -1) {
            return state;
          }
          const clamped = Math.max(0, Math.min(toIndex, state.overlays.length - 1));
          if (clamped === fromIndex) {
            return state;
          }
          const overlays = [...state.overlays];
          const [moved] = overlays.splice(fromIndex, 1);
          overlays.splice(clamped, 0, moved!);
          return { overlays };
        });
      },

      clearOverlays: () => {
        set({ overlays: [], nextColorIndex: 0 });
      },
    }),
    {
      name: 'indicator-overlays',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
