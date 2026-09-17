import fs from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ENV_TS_PATH = path.resolve(__dirname, 'env.ts');

describe('env.ts source shape — guards the NEXT_PUBLIC_* build-time-inlining bug', () => {
  // Next.js's NEXT_PUBLIC_* replacement is a STATIC find-and-inline pass over
  // the source text at build time; it can only see `process.env.NEXT_PUBLIC_X`
  // written out literally. Vitest runs this file as plain Node code with a
  // real `process.env` object, so it CANNOT distinguish
  // `envSchema.safeParse(process.env)` from the correct, explicit form at
  // runtime — both parse identically in a test. That's exactly how this bug
  // shipped undetected: every existing check (typecheck, `next dev`, a
  // hypothetical naive unit test) looks fine, and only a real `next build`
  // reveals the built bundle has zero trace of the configured value (see
  // this fix's own commit for the actual grep-based proof). So the only
  // thing a fast, in-suite test CAN meaningfully guard is the source text
  // itself — asserting a regression back to the whole-object form fails
  // this test immediately, rather than shipping silently again.
  const source = fs.readFileSync(ENV_TS_PATH, 'utf-8');

  it('references every NEXT_PUBLIC_* variable by its literal name', () => {
    expect(source).toContain('process.env.NEXT_PUBLIC_API_URL');
    expect(source).toContain('process.env.NEXT_PUBLIC_WS_URL');
    expect(source).toContain('process.env.NEXT_PUBLIC_APP_NAME');
  });

  it('never passes the whole `process.env` object to the schema', () => {
    expect(source).not.toMatch(/safeParse\(\s*process\.env\s*\)/);
  });
});

describe('env — runtime parsing behavior', () => {
  const ORIGINAL_ENV = { ...process.env };

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...ORIGINAL_ENV };
    delete process.env.NEXT_PUBLIC_API_URL;
    delete process.env.NEXT_PUBLIC_WS_URL;
    delete process.env.NEXT_PUBLIC_APP_NAME;
  });

  afterEach(() => {
    process.env = { ...ORIGINAL_ENV };
  });

  it('falls back to the documented defaults when nothing is set', async () => {
    const { env } = await import('./env');
    expect(env.NEXT_PUBLIC_API_URL).toBe('http://localhost:8000');
    expect(env.NEXT_PUBLIC_WS_URL).toBe('wss://public-socket.india.delta.exchange');
    expect(env.NEXT_PUBLIC_APP_NAME).toBe('Research Dashboard');
  });

  it('uses each real value when set, not the default', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.example.com';
    process.env.NEXT_PUBLIC_WS_URL = 'wss://ws.example.com';
    process.env.NEXT_PUBLIC_APP_NAME = 'Custom Dashboard';
    const { env } = await import('./env');
    expect(env.NEXT_PUBLIC_API_URL).toBe('https://api.example.com');
    expect(env.NEXT_PUBLIC_WS_URL).toBe('wss://ws.example.com');
    expect(env.NEXT_PUBLIC_APP_NAME).toBe('Custom Dashboard');
  });

  it('throws with a clear message when a set value is invalid', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'not-a-url';
    await expect(import('./env')).rejects.toThrow(/Invalid dashboard environment/);
  });
});
