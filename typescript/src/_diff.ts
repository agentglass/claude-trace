export interface TraceDiff {
  readonly addedToolCalls: readonly string[];
  readonly removedToolCalls: readonly string[];
  readonly tokenDelta: number;
  readonly turnDelta: number;
  isEquivalent(): boolean;
  summary(): string;
  assertEquivalent(): void;
}

export class TraceSnapshot {
  readonly traceId: string;
  readonly toolCalls: readonly string[];
  readonly turnCount: number;
  readonly totalTokens: number;
  readonly stopReason: string;

  constructor(opts: {
    traceId: string;
    toolCalls: string[];
    turnCount: number;
    totalTokens: number;
    stopReason: string;
  }) {
    this.traceId = opts.traceId;
    this.toolCalls = opts.toolCalls;
    this.turnCount = opts.turnCount;
    this.totalTokens = opts.totalTokens;
    this.stopReason = opts.stopReason;
  }
}

class TraceDiffImpl implements TraceDiff {
  readonly addedToolCalls: readonly string[];
  readonly removedToolCalls: readonly string[];
  readonly tokenDelta: number;
  readonly turnDelta: number;

  constructor(a: TraceSnapshot, b: TraceSnapshot) {
    const setA = new Set(a.toolCalls);
    const setB = new Set(b.toolCalls);
    this.addedToolCalls = [...b.toolCalls].filter(t => !setA.has(t));
    this.removedToolCalls = [...a.toolCalls].filter(t => !setB.has(t));
    this.tokenDelta = b.totalTokens - a.totalTokens;
    this.turnDelta = b.turnCount - a.turnCount;
  }

  isEquivalent(): boolean {
    return this.addedToolCalls.length === 0
      && this.removedToolCalls.length === 0
      && this.tokenDelta === 0
      && this.turnDelta === 0;
  }

  summary(): string {
    const parts: string[] = [];
    if (this.addedToolCalls.length > 0) {
      parts.push(`added tool calls: ${this.addedToolCalls.join(', ')}`);
    }
    if (this.removedToolCalls.length > 0) {
      parts.push(`removed tool calls: ${this.removedToolCalls.join(', ')}`);
    }
    if (this.tokenDelta !== 0) {
      parts.push(`token delta: ${this.tokenDelta > 0 ? '+' : ''}${this.tokenDelta}`);
    }
    if (this.turnDelta !== 0) {
      parts.push(`turn delta: ${this.turnDelta > 0 ? '+' : ''}${this.turnDelta}`);
    }
    return parts.length === 0 ? 'traces are equivalent' : parts.join('; ');
  }

  assertEquivalent(): void {
    if (!this.isEquivalent()) {
      throw new Error(`Trace diff: ${this.summary()}`);
    }
  }
}

/** Compare two trace snapshots and return a structured diff. */
export function compareTraces(a: TraceSnapshot, b: TraceSnapshot): TraceDiff {
  return new TraceDiffImpl(a, b);
}
