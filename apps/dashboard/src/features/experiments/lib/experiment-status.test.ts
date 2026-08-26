import { describe, expect, it } from 'vitest';
import { STATUS_COLORS, statusLabel } from './experiment-status';

describe('statusLabel', () => {
  it('capitalizes the first letter of a status', () => {
    expect(statusLabel('draft')).toBe('Draft');
    expect(statusLabel('running')).toBe('Running');
    expect(statusLabel('archived')).toBe('Archived');
  });

  it('accepts an arbitrary string, not just a known status', () => {
    expect(statusLabel('custom_status')).toBe('Custom_status');
  });
});

describe('STATUS_COLORS', () => {
  it('defines a color for every experiment status', () => {
    expect(Object.keys(STATUS_COLORS).sort()).toEqual(
      ['archived', 'completed', 'draft', 'failed', 'running'].sort(),
    );
  });

  it('gives failed a distinct error color', () => {
    expect(STATUS_COLORS.failed).toBe('error');
  });
});
