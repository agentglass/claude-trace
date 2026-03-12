"""TraceConfig: configuration for claude-trace instrumentation.

All fields have safe defaults. Sensitive content is never captured unless
explicitly opted in via ``capture_content=True``.

Environment variables:
    CLAUDE_TRACE_CAPTURE_CONTENT  - "true"/"false" (default: "false")
    CLAUDE_TRACE_MAX_ATTR_LENGTH  - int (default: 512)
    CLAUDE_TRACE_SANITIZE         - "true"/"false" (default: "false")
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class TraceConfig:
    """Configuration for claude-trace instrumentation.

    All fields have safe defaults. Sensitive content is never captured
    unless explicitly opted in.

    Attributes:
        capture_content: Capture raw prompt/response text. Default False (PII protection).
        max_attribute_length: Max characters for any string span attribute. Default 512.
        sanitize: Strip all text content from spans. Overrides capture_content.
    """

    capture_content: bool = False
    max_attribute_length: int = 512
    sanitize: bool = False

    @classmethod
    def from_env(cls) -> "TraceConfig":
        """Create config reading CLAUDE_TRACE_* environment variables.

        Returns:
            TraceConfig populated from environment variables with safe defaults.
        """
        return cls(
            capture_content=os.getenv("CLAUDE_TRACE_CAPTURE_CONTENT", "").lower() == "true",
            max_attribute_length=int(os.getenv("CLAUDE_TRACE_MAX_ATTR_LENGTH", "512")),
            sanitize=os.getenv("CLAUDE_TRACE_SANITIZE", "").lower() == "true",
        )
