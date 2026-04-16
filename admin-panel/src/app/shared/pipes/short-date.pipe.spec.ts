import { ShortDatePipe } from './short-date.pipe';

describe('ShortDatePipe', () => {
  const pipe = new ShortDatePipe();

  it('returns em-dash for null/undefined', () => {
    expect(pipe.transform(null)).toBe('—');
    expect(pipe.transform(undefined)).toBe('—');
  });

  it('returns "just now" for very recent times', () => {
    expect(pipe.transform(new Date())).toBe('just now');
  });

  it('returns minutes for <1h', () => {
    const d = new Date(Date.now() - 5 * 60_000);
    expect(pipe.transform(d)).toBe('5m ago');
  });
});
