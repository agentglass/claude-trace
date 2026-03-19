/**
 * claude-trace: Zero-configuration OpenTelemetry observability for Claude Agent SDK.
 *
 * @example
 * ```typescript
 * import { instrument } from 'claude-trace';
 * import Anthropic from '@anthropic-ai/sdk';
 *
 * instrument();
 * const client = new Anthropic();
 * // All client.messages.create() calls are now traced
 * ```
 */

export { instrument, uninstrument } from './_instrument';
export { session, currentSession } from './_session';
export { TraceConfig } from './_config';
export { TraceSnapshot, compareTraces } from './_diff';
export { calculateCost, type CostBreakdown } from './_cost';
export type { TraceDiff } from './_diff';
export type { AgentSession } from './_session';
