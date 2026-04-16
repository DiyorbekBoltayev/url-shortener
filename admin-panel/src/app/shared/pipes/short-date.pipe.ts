import { Pipe, PipeTransform } from '@angular/core';

/**
 * Formats ISO-8601 timestamps as either:
 *   - relative ("3m ago", "2h ago") for recent events
 *   - localized short date for older ones
 */
@Pipe({ name: 'shortDate', standalone: true })
export class ShortDatePipe implements PipeTransform {
  transform(value: string | Date | null | undefined): string {
    if (!value) return '—';
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return '—';

    const diffMs = Date.now() - d.getTime();
    const sec = Math.max(0, Math.round(diffMs / 1000));
    if (sec < 45) return 'just now';
    const min = Math.round(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const days = Math.round(hr / 24);
    if (days < 7) return `${days}d ago`;

    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }
}
