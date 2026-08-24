/**
 * Triggers a browser file download for an in-memory `Blob` via a
 * temporary, invisible anchor — the standard client-side download pattern,
 * promoted out of the History page's CSV/JSON export once the Technical
 * Indicators page needed the identical behavior.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
