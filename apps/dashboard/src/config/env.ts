import { z } from 'zod';

const envSchema = z.object({
  NEXT_PUBLIC_API_URL: z.url().default('http://localhost:8000'),
  NEXT_PUBLIC_WS_URL: z.url().default('wss://public-socket.india.delta.exchange'),
  NEXT_PUBLIC_APP_NAME: z.string().min(1).default('Research Dashboard'),
});

// Referenced by literal name, not the whole `process.env` object — Next.js's
// build-time NEXT_PUBLIC_* replacement is a static find-and-inline pass over
// the source text; it can only see `process.env.NEXT_PUBLIC_X` written out
// directly. Passing the whole object here defeated that detection: none of
// these three values ever made it into the built bundle, and every
// deployment silently fell back to the defaults above. Confirmed live before
// this fix — a real Docker build with a real NEXT_PUBLIC_API_URL build arg
// produced a `.next/` output with zero trace of that value.
const parsed = envSchema.safeParse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL,
  NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME,
});

if (!parsed.success) {
  throw new Error(
    `Invalid dashboard environment: ${parsed.error.issues
      .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
      .join('; ')}`,
  );
}

export const env = parsed.data;
