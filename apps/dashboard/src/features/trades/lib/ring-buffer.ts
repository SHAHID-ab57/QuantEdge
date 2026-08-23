/**
 * A fixed-capacity circular buffer: `push` is O(1) amortized and never
 * copies existing elements, unlike an array-based "append then slice"
 * buffer (the approach this replaced — see `rolling-window.ts`'s history
 * for why that mattered under a busy market). Once full, the oldest entry
 * is silently overwritten by the newest push.
 *
 * This is a *capacity* bound, not a *time* bound — callers that need a
 * time-windowed view (e.g. "the last 15 minutes of trades") must still
 * filter `toArray()`'s output by timestamp themselves. The capacity only
 * needs to be generous enough that a real trading session can never
 * produce more items in its actual retention window than the buffer can
 * hold; see each call site for the sizing rationale.
 */
export class RingBuffer<T> {
  private readonly buffer: (T | undefined)[];
  private head = 0;
  private length = 0;

  constructor(private readonly capacity: number) {
    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new RangeError('RingBuffer capacity must be a positive integer');
    }
    this.buffer = new Array<T | undefined>(capacity);
  }

  get size(): number {
    return this.length;
  }

  get isFull(): boolean {
    return this.length === this.capacity;
  }

  /** Appends one item, overwriting the oldest entry once full. O(1). */
  push(item: T): void {
    const index = (this.head + this.length) % this.capacity;
    this.buffer[index] = item;
    if (this.length < this.capacity) {
      this.length += 1;
    } else {
      this.head = (this.head + 1) % this.capacity;
    }
  }

  /** Oldest-to-newest iteration — the same order items were pushed in. */
  *[Symbol.iterator](): IterableIterator<T> {
    for (let i = 0; i < this.length; i += 1) {
      yield this.buffer[(this.head + i) % this.capacity] as T;
    }
  }

  /** Oldest-to-newest snapshot as a plain array — the one O(size) copy per read, not per write. */
  toArray(): T[] {
    return [...this];
  }

  clear(): void {
    this.head = 0;
    this.length = 0;
  }
}
