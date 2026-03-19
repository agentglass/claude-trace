/**
 * Configuration for claude-trace instrumentation.
 * All fields default to safe values that protect PII.
 */
export class TraceConfig {
  /** Capture raw prompt/response text. Default false (PII protection). */
  readonly captureContent: boolean;
  /** Max characters for any string span attribute. Default 512. */
  readonly maxAttributeLength: number;
  /** Strip all text content from spans. Overrides captureContent. */
  readonly sanitize: boolean;

  constructor(options: {
    captureContent?: boolean;
    maxAttributeLength?: number;
    sanitize?: boolean;
  } = {}) {
    this.captureContent = options.captureContent ?? false;
    this.maxAttributeLength = options.maxAttributeLength ?? 512;
    this.sanitize = options.sanitize ?? false;
  }

  /** Create config reading CLAUDE_TRACE_* environment variables. */
  static fromEnv(): TraceConfig {
    return new TraceConfig({
      captureContent: process.env['CLAUDE_TRACE_CAPTURE_CONTENT']?.toLowerCase() === 'true',
      maxAttributeLength: process.env['CLAUDE_TRACE_MAX_ATTR_LENGTH'] != null
        ? parseInt(process.env['CLAUDE_TRACE_MAX_ATTR_LENGTH'], 10)
        : 512,
      sanitize: process.env['CLAUDE_TRACE_SANITIZE']?.toLowerCase() === 'true',
    });
  }
}
