import type { Span } from '@opentelemetry/api';
import { trace, context, SpanStatusCode } from '@opentelemetry/api';
import type { TraceConfig } from './_config';
import { currentSession } from './_session';
import { calculateCost } from './_cost';

const TRACER_NAME = 'claude-trace';

/** @internal */
export function truncate(value: string, maxLen: number): string {
  if (value.length <= maxLen) return value;
  const over = value.length - maxLen;
  return `${value.slice(0, maxLen)}...[truncated ${over} chars]`;
}

/** @internal */
export function redactApiKeys(value: string): string {
  return value.replace(/sk-ant-[A-Za-z0-9\-_]+/g, '[REDACTED]');
}

type AnyFn = (...args: unknown[]) => unknown;
let _origCreate: AnyFn | undefined;

function extractUsage(response: unknown): [number, number, number, number] {
  if (response == null || typeof response !== 'object') return [0, 0, 0, 0];
  const r = response as Record<string, unknown>;
  const usage = r['usage'];
  if (usage == null || typeof usage !== 'object') return [0, 0, 0, 0];
  const u = usage as Record<string, unknown>;
  return [
    typeof u['input_tokens'] === 'number' ? u['input_tokens'] : 0,
    typeof u['output_tokens'] === 'number' ? u['output_tokens'] : 0,
    typeof u['cache_read_input_tokens'] === 'number' ? u['cache_read_input_tokens'] : 0,
    typeof u['cache_creation_input_tokens'] === 'number' ? u['cache_creation_input_tokens'] : 0,
  ];
}

function setTurnAttributes(span: Span, response: unknown, config: TraceConfig, latencyMs: number): void {
  if (response == null || typeof response !== 'object') return;
  const r = response as Record<string, unknown>;

  const model = typeof r['model'] === 'string' ? r['model'] : 'unknown';
  const stopReason = typeof r['stop_reason'] === 'string' ? r['stop_reason'] : 'unknown';
  const [inputTok, outputTok, cacheRead, cacheWrite] = extractUsage(response);

  span.setAttribute('claude.turn.model', truncate(model, config.maxAttributeLength));
  span.setAttribute('claude.turn.stop_reason', stopReason);
  span.setAttribute('claude.turn.input_tokens', inputTok);
  span.setAttribute('claude.turn.output_tokens', outputTok);
  span.setAttribute('claude.turn.cache_read_tokens', cacheRead);
  span.setAttribute('claude.turn.cache_creation_tokens', cacheWrite);
  span.setAttribute('claude.turn.latency_ms', Math.round(latencyMs * 100) / 100);
}

/**
 * Instrument the Anthropic SDK. Call once at application startup.
 *
 * @example
 * ```typescript
 * import { instrument } from 'claude-trace';
 * instrument();
 * ```
 */
export function instrument(config: TraceConfig): void {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const sdk = require('@anthropic-ai/sdk') as { default: { prototype: Record<string, unknown> } };
    const Messages = (sdk.default as unknown as Record<string, { prototype: Record<string, AnyFn> }>)['Messages'];
    if (Messages == null) return;

    const proto = Messages.prototype;
    if (_origCreate != null) return; // already instrumented

    _origCreate = proto['create'] as AnyFn;
    proto['create'] = function (...args: unknown[]) {
      const tracer = trace.getTracer(TRACER_NAME);
      const sess = currentSession();
      const parentCtx = sess?.span != null
        ? trace.setSpan(context.active(), sess.span)
        : context.active();

      const span = tracer.startSpan('claude.agent.turn', {}, parentCtx);
      const start = performance.now();

      return context.with(trace.setSpan(parentCtx, span), () => {
        const result = (_origCreate as AnyFn).apply(this, args) as Promise<unknown>;
        return Promise.resolve(result).then(
          (response) => {
            const latencyMs = performance.now() - start;
            setTurnAttributes(span, response, config, latencyMs);
            span.setStatus({ code: SpanStatusCode.OK });

            if (sess != null) {
              const [inputTok, outputTok, cacheRead, cacheWrite] = extractUsage(response);
              const model = (response as Record<string, unknown>)['model'];
              try {
                const cost = calculateCost(
                  typeof model === 'string' ? model : 'unknown',
                  inputTok, outputTok, cacheRead, cacheWrite,
                );
                sess._recordTurn(inputTok, outputTok, cacheRead, cacheWrite, cost.totalUsd);
              } catch {
                sess._recordTurn(inputTok, outputTok, cacheRead, cacheWrite, 0);
              }
            }
            span.end();
            return response;
          },
          (err: unknown) => {
            const latencyMs = performance.now() - start;
            span.setAttribute('claude.turn.latency_ms', Math.round(latencyMs * 100) / 100);
            span.setAttribute('claude.turn.error_type', err instanceof Error ? err.constructor.name : 'UnknownError');
            const msg = err instanceof Error
              ? truncate(redactApiKeys(err.message), config.maxAttributeLength)
              : 'unknown error';
            span.setAttribute('claude.turn.error_message', msg);
            span.setStatus({ code: SpanStatusCode.ERROR, message: msg });
            span.end();
            throw err;
          },
        );
      });
    };
  } catch {
    // Anthropic SDK not installed — instrument() is a no-op
  }
}

/** Remove all patches applied by instrument(). */
export function uninstrument(): void {
  if (_origCreate == null) return;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const sdk = require('@anthropic-ai/sdk') as { default: { prototype: Record<string, unknown> } };
    const Messages = (sdk.default as unknown as Record<string, { prototype: Record<string, AnyFn> }>)['Messages'];
    if (Messages != null) {
      Messages.prototype['create'] = _origCreate;
    }
  } catch { /* no-op */ }
  _origCreate = undefined;
}
