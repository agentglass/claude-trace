import { calculateCost, TraceConfig } from '../src/index';

// NOTE: These tests use the pure-TS cost calculator (no WASM needed for unit tests)
// WASM integration tests are in tests/wasm.test.ts

describe('calculateCost', () => {
  it('throws for unknown model', () => {
    expect(() => calculateCost('gpt-totally-fake', 100, 100)).toThrow();
  });

  it('returns zero cost for zero tokens', () => {
    const cost = calculateCost('claude-sonnet-4-6', 0, 0);
    expect(cost.totalUsd).toBe(0);
  });
});

describe('TraceConfig', () => {
  it('defaults captureContent to false', () => {
    const cfg = new TraceConfig();
    expect(cfg.captureContent).toBe(false);
  });

  it('defaults sanitize to false', () => {
    const cfg = new TraceConfig();
    expect(cfg.sanitize).toBe(false);
  });

  it('defaults maxAttributeLength to 512', () => {
    const cfg = new TraceConfig();
    expect(cfg.maxAttributeLength).toBe(512);
  });

  it('reads CLAUDE_TRACE_SANITIZE env var', () => {
    process.env['CLAUDE_TRACE_SANITIZE'] = 'true';
    const cfg = TraceConfig.fromEnv();
    expect(cfg.sanitize).toBe(true);
    delete process.env['CLAUDE_TRACE_SANITIZE'];
  });
});
