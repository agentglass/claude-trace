import { trace, context, SpanStatusCode } from '@opentelemetry/api';
import type { Span, Context } from '@opentelemetry/api';
import type { TraceConfig } from './_config';

const TRACER_NAME = 'claude-trace';

let _currentSession: AgentSession | undefined;

export class AgentSession {
  readonly name: string;
  readonly span: Span;
  private readonly _config: TraceConfig;
  private readonly _prevContext: Context;
  totalInputTokens = 0;
  totalOutputTokens = 0;
  totalCacheReadTokens = 0;
  totalCacheWriteTokens = 0;
  totalCostUsd = 0;
  turnCount = 0;

  constructor(
    name: string,
    opts: { customerId?: string; tags?: string[]; config: TraceConfig },
  ) {
    this.name = name;
    this._config = opts.config;
    this._prevContext = context.active();

    const tracer = trace.getTracer(TRACER_NAME);
    this.span = tracer.startSpan('claude.agent.session');
    this.span.setAttribute('claude.session.name', name);
    if (opts.customerId != null && !opts.config.sanitize) {
      this.span.setAttribute('claude.session.customer_id', opts.customerId);
    }
    if (opts.tags != null && opts.tags.length > 0) {
      this.span.setAttribute('claude.session.tags', opts.tags.join(','));
    }
  }

  /** @internal Called by the instrumentation layer after each API call. */
  _recordTurn(
    inputTokens: number,
    outputTokens: number,
    cacheRead: number,
    cacheWrite: number,
    costUsd: number,
  ): void {
    this.totalInputTokens += inputTokens;
    this.totalOutputTokens += outputTokens;
    this.totalCacheReadTokens += cacheRead;
    this.totalCacheWriteTokens += cacheWrite;
    this.totalCostUsd += costUsd;
    this.turnCount += 1;
  }

  end(error?: Error): void {
    this.span.setAttribute('claude.session.total_input_tokens', this.totalInputTokens);
    this.span.setAttribute('claude.session.total_output_tokens', this.totalOutputTokens);
    this.span.setAttribute('claude.session.turn_count', this.turnCount);
    this.span.setAttribute('claude.session.estimated_cost_usd', this.totalCostUsd.toFixed(6));
    if (error != null) {
      this.span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
    } else {
      this.span.setStatus({ code: SpanStatusCode.OK });
    }
    this.span.end();
    _currentSession = undefined;
  }
}

/** Return the active AgentSession, or undefined. */
export function currentSession(): AgentSession | undefined {
  return _currentSession;
}

/**
 * Run a callback within a named agent session.
 *
 * @example
 * ```typescript
 * const result = await session('billing-agent', { customerId: 'acme' }, async (sess) => {
 *   const response = await client.messages.create({...});
 *   return response;
 * });
 * ```
 */
export async function session<T>(
  name: string,
  opts: { customerId?: string; tags?: string[]; config?: TraceConfig },
  fn: (sess: AgentSession) => Promise<T>,
): Promise<T> {
  const { TraceConfig } = await import('./_config');
  const cfg = opts.config ?? TraceConfig.fromEnv();
  const sess = new AgentSession(name, { ...opts, config: cfg });
  _currentSession = sess;
  try {
    const result = await fn(sess);
    sess.end();
    return result;
  } catch (err) {
    sess.end(err instanceof Error ? err : new Error(String(err)));
    throw err;
  }
}
