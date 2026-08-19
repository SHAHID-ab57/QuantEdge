export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—';
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

export function formatPrice(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(parsed);
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

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(iso));
}
