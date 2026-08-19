import { z } from 'zod';

const envSchema = z.object({
  NEXT_PUBLIC_API_URL: z.url().default('http://localhost:8000'),
  NEXT_PUBLIC_WS_URL: z.url().default('wss://public-socket.india.delta.exchange'),
  NEXT_PUBLIC_APP_NAME: z.string().min(1).default('Research Dashboard'),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
  throw new Error(
    `Invalid dashboard environment: ${parsed.error.issues
      .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
      .join('; ')}`,
  );
}

export const env = parsed.data;
