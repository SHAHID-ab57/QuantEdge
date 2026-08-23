import { describe, expect, it } from 'vitest';
import { RingBuffer } from './ring-buffer';

describe('RingBuffer', () => {
  it('starts empty', () => {
    const buffer = new RingBuffer<number>(3);
    expect(buffer.size).toBe(0);
    expect(buffer.isFull).toBe(false);
    expect(buffer.toArray()).toEqual([]);
  });

  it('rejects a non-positive or non-integer capacity', () => {
    expect(() => new RingBuffer(0)).toThrow(RangeError);
    expect(() => new RingBuffer(-1)).toThrow(RangeError);
    expect(() => new RingBuffer(1.5)).toThrow(RangeError);
  });

  it('preserves insertion order while not yet full', () => {
    const buffer = new RingBuffer<number>(5);
    buffer.push(1);
    buffer.push(2);
    buffer.push(3);
    expect(buffer.toArray()).toEqual([1, 2, 3]);
    expect(buffer.size).toBe(3);
    expect(buffer.isFull).toBe(false);
  });

  it('overwrites the oldest entry once full, never growing past capacity', () => {
    const buffer = new RingBuffer<number>(3);
    buffer.push(1);
    buffer.push(2);
    buffer.push(3);
    expect(buffer.isFull).toBe(true);
    buffer.push(4);
    expect(buffer.toArray()).toEqual([2, 3, 4]);
    expect(buffer.size).toBe(3);
  });

  it('keeps overwriting correctly across many wraps', () => {
    const buffer = new RingBuffer<number>(4);
    for (let i = 0; i < 50; i += 1) {
      buffer.push(i);
    }
    expect(buffer.toArray()).toEqual([46, 47, 48, 49]);
  });

  it('is iterable directly, not just via toArray', () => {
    const buffer = new RingBuffer<number>(3);
    buffer.push(1);
    buffer.push(2);
    expect([...buffer]).toEqual([1, 2]);
  });

  it('clear() empties the buffer and resets capacity tracking', () => {
    const buffer = new RingBuffer<number>(2);
    buffer.push(1);
    buffer.push(2);
    buffer.push(3);
    buffer.clear();
    expect(buffer.size).toBe(0);
    expect(buffer.toArray()).toEqual([]);
    buffer.push(9);
    expect(buffer.toArray()).toEqual([9]);
  });
});
