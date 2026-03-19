import { TraceSnapshot, compareTraces } from '../src/index';

describe('compareTraces', () => {
  const makeSnap = (overrides: Partial<ConstructorParameters<typeof TraceSnapshot>[0]> = {}) =>
    new TraceSnapshot({
      traceId: 'test',
      toolCalls: [],
      turnCount: 1,
      totalTokens: 500,
      stopReason: 'end_turn',
      ...overrides,
    });

  it('identical snapshots are equivalent', () => {
    const snap = makeSnap();
    expect(compareTraces(snap, snap).isEquivalent()).toBe(true);
  });

  it('detects added tool calls', () => {
    const a = makeSnap({ toolCalls: ['bash'] });
    const b = makeSnap({ toolCalls: ['bash', 'read_file'] });
    const diff = compareTraces(a, b);
    expect(diff.addedToolCalls).toContain('read_file');
    expect(diff.isEquivalent()).toBe(false);
  });

  it('detects removed tool calls', () => {
    const a = makeSnap({ toolCalls: ['bash', 'web_search'] });
    const b = makeSnap({ toolCalls: ['bash'] });
    expect(compareTraces(a, b).removedToolCalls).toContain('web_search');
  });

  it('calculates token delta', () => {
    const a = makeSnap({ totalTokens: 1000 });
    const b = makeSnap({ totalTokens: 1200 });
    expect(compareTraces(a, b).tokenDelta).toBe(200);
  });

  it('assertEquivalent throws when different', () => {
    const a = makeSnap({ toolCalls: ['bash'] });
    const b = makeSnap({ toolCalls: ['read_file'] });
    expect(() => compareTraces(a, b).assertEquivalent()).toThrow();
  });
});
