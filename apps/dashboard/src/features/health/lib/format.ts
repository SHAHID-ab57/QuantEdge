export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—';
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86_400);
  const hours = Math.floor((total % 86_400) / 3_600);
  const minutes = Math.floor((total % 3_600) / 60);
  const secs = total % 60;
  const parts: string[] = [];
  if (days > 0) {
    parts.push(`${days}d`);
  }
  if (hours > 0 || days > 0) {
    parts.push(`${hours}h`);
  }
  if (minutes > 0 || hours > 0) {
    parts.push(`${minutes}m`);
  }
  parts.push(`${secs}s`);
  return parts.join(' ');
}

export function formatRelative(iso: string | null | undefined, now: number): string {
  if (!iso) {
    return '—';
  }
  const elapsedSeconds = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (elapsedSeconds < 1) {
    return 'just now';
  }
  if (elapsedSeconds < 10) {
    return `${elapsedSeconds.toFixed(1)}s ago`;
  }
  if (elapsedSeconds < 60) {
    return `${Math.floor(elapsedSeconds)}s ago`;
  }
  if (elapsedSeconds < 3_600) {
    return `${Math.floor(elapsedSeconds / 60)}m ago`;
  }
  if (elapsedSeconds < 86_400) {
    return `${Math.floor(elapsedSeconds / 3_600)}h ago`;
  }
  return `${Math.floor(elapsedSeconds / 86_400)}d ago`;
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) {
    return '—';
  }
  if (ms < 1) {
    return `${(ms * 1000).toFixed(0)}µs`;
  }
  if (ms < 1000) {
    return `${ms.toFixed(ms < 10 ? 2 : 1)}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(iso));
}
