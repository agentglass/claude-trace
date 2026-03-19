import { redactApiKeys, truncate } from '../src/_instrument';

describe('redactApiKeys', () => {
  it('redacts sk-ant- prefixed keys', () => {
    const result = redactApiKeys('Bearer sk-ant-api03-abc123xyz');
    expect(result).not.toContain('sk-ant');
    expect(result).toContain('[REDACTED]');
  });

  it('leaves non-key text unchanged', () => {
    expect(redactApiKeys('Error: bad request')).toBe('Error: bad request');
  });

  it('redacts multiple keys in one string', () => {
    const text = 'key1=sk-ant-abc key2=sk-ant-xyz';
    const result = redactApiKeys(text);
    expect((result.match(/\[REDACTED\]/g) ?? []).length).toBe(2);
  });
});

describe('truncate', () => {
  it('leaves short strings unchanged', () => {
    expect(truncate('hello', 512)).toBe('hello');
  });

  it('truncates long strings with suffix', () => {
    const s = 'x'.repeat(600);
    const result = truncate(s, 512);
    expect(result.length).toBeLessThan(600);
    expect(result).toContain('truncated');
  });

  it('handles exact boundary', () => {
    const s = 'x'.repeat(512);
    expect(truncate(s, 512)).toBe(s);
  });
});
