export interface CostBreakdown {
  readonly inputUsd: number;
  readonly outputUsd: number;
  readonly cacheReadUsd: number;
  readonly cacheWriteUsd: number;
  readonly totalUsd: number;
}

interface ModelPricing {
  inputPerMtok: number;
  outputPerMtok: number;
  cacheReadPerMtok: number;
  cacheWritePerMtok: number;
}

const PRICING: ReadonlyMap<string, ModelPricing> = new Map([
  ['claude-opus-4',       { inputPerMtok: 15.00, outputPerMtok: 75.00, cacheReadPerMtok: 1.50,  cacheWritePerMtok: 18.75 }],
  ['claude-opus-4-5',     { inputPerMtok: 15.00, outputPerMtok: 75.00, cacheReadPerMtok: 1.50,  cacheWritePerMtok: 18.75 }],
  ['claude-sonnet-4-6',   { inputPerMtok:  3.00, outputPerMtok: 15.00, cacheReadPerMtok: 0.30,  cacheWritePerMtok:  3.75 }],
  ['claude-sonnet-4-5',   { inputPerMtok:  3.00, outputPerMtok: 15.00, cacheReadPerMtok: 0.30,  cacheWritePerMtok:  3.75 }],
  ['claude-haiku-4-5',    { inputPerMtok:  0.80, outputPerMtok:  4.00, cacheReadPerMtok: 0.08,  cacheWritePerMtok:  1.00 }],
  ['claude-3-5-sonnet-20241022', { inputPerMtok: 3.00, outputPerMtok: 15.00, cacheReadPerMtok: 0.30, cacheWritePerMtok: 3.75 }],
  ['claude-3-5-haiku-20241022',  { inputPerMtok: 0.80, outputPerMtok:  4.00, cacheReadPerMtok: 0.08, cacheWritePerMtok: 1.00 }],
  ['claude-3-opus-20240229',     { inputPerMtok: 15.00, outputPerMtok: 75.00, cacheReadPerMtok: 1.50, cacheWritePerMtok: 18.75 }],
]);

function resolveModel(model: string): ModelPricing {
  const exact = PRICING.get(model);
  if (exact != null) return exact;

  // Prefix match: longest prefix wins
  let bestMatch: ModelPricing | undefined;
  let bestLen = 0;
  for (const [key, pricing] of PRICING) {
    if (model.startsWith(key) && key.length > bestLen) {
      bestMatch = pricing;
      bestLen = key.length;
    }
  }
  if (bestMatch != null) return bestMatch;
  throw new Error(`Model '${model}' not found in pricing table`);
}

/**
 * Calculate USD cost for a Claude API call.
 * @throws {Error} if the model is not recognized
 */
export function calculateCost(
  model: string,
  inputTokens: number,
  outputTokens: number,
  cacheReadTokens = 0,
  cacheWriteTokens = 0,
): CostBreakdown {
  const p = resolveModel(model);
  const M = 1_000_000;
  const inputUsd = (inputTokens / M) * p.inputPerMtok;
  const outputUsd = (outputTokens / M) * p.outputPerMtok;
  const cacheReadUsd = (cacheReadTokens / M) * p.cacheReadPerMtok;
  const cacheWriteUsd = (cacheWriteTokens / M) * p.cacheWritePerMtok;
  return {
    inputUsd,
    outputUsd,
    cacheReadUsd,
    cacheWriteUsd,
    totalUsd: inputUsd + outputUsd + cacheReadUsd + cacheWriteUsd,
  };
}
