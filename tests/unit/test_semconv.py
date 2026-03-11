"""
Unit tests for claude-trace semantic conventions.

Verifies:
    1. All attribute names follow the ``claude.{category}.{name}`` pattern.
    2. No duplicate attribute names across all categories.
    3. Every category exposes the required core attributes.
    4. Attribute name constants are strings.
    5. All dataclass instances are frozen (immutable).
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

import pytest

from claude_trace._semconv.claude import (
    CostAttributes,
    SessionAttributes,
    ToolAttributes,
    TurnAttributes,
)

# Pattern: must start with "claude." and be all lowercase dot-separated words
_ATTR_PATTERN = re.compile(r"^claude\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def _get_attr_values(cls: Any) -> list[str]:
    """Extract all string field values from a frozen dataclass instance."""
    instance = cls()
    return [
        getattr(instance, f.name)
        for f in dataclasses.fields(instance)
        if isinstance(getattr(instance, f.name), str)
    ]


class TestAttributeNameFormat:
    """Verify all attribute names conform to the claude.{cat}.{name} pattern."""

    @pytest.mark.parametrize(
        "attr_class",
        [SessionAttributes, TurnAttributes, ToolAttributes, CostAttributes],
    )
    def test_all_values_match_pattern(self, attr_class: Any) -> None:
        values = _get_attr_values(attr_class)
        assert values, f"{attr_class.__name__} has no string fields"
        for val in values:
            assert _ATTR_PATTERN.match(val), (
                f"{attr_class.__name__}: attribute name {val!r} does not match "
                f"pattern 'claude.{{category}}.{{name}}'"
            )

    @pytest.mark.parametrize(
        "attr_class",
        [SessionAttributes, TurnAttributes, ToolAttributes, CostAttributes],
    )
    def test_all_values_are_strings(self, attr_class: Any) -> None:
        values = _get_attr_values(attr_class)
        for val in values:
            assert isinstance(val, str), f"Expected str, got {type(val)} for {val!r}"

    @pytest.mark.parametrize(
        "attr_class",
        [SessionAttributes, TurnAttributes, ToolAttributes, CostAttributes],
    )
    def test_all_values_are_lowercase(self, attr_class: Any) -> None:
        values = _get_attr_values(attr_class)
        for val in values:
            assert val == val.lower(), f"Attribute {val!r} contains uppercase characters"


class TestNoDuplicates:
    """Verify no attribute name appears in more than one category."""

    def test_no_cross_category_duplicates(self) -> None:
        all_values: list[str] = []
        for cls in [SessionAttributes, TurnAttributes, ToolAttributes, CostAttributes]:
            all_values.extend(_get_attr_values(cls))

        seen: set[str] = set()
        duplicates: list[str] = []
        for val in all_values:
            if val in seen:
                duplicates.append(val)
            seen.add(val)

        assert not duplicates, f"Duplicate attribute names found: {duplicates}"

    def test_no_within_category_duplicates(self) -> None:
        for cls in [SessionAttributes, TurnAttributes, ToolAttributes, CostAttributes]:
            values = _get_attr_values(cls)
            assert len(values) == len(set(values)), (
                f"{cls.__name__} has duplicate values: "
                f"{[v for v in values if values.count(v) > 1]}"
            )


class TestRequiredAttributes:
    """Verify required core attributes are present in each category."""

    def test_session_required_attrs(self) -> None:
        sess = SessionAttributes()
        assert sess.SESSION_ID.startswith("claude.session.")
        assert sess.MODEL.startswith("claude.session.")
        assert sess.STATUS.startswith("claude.session.")
        assert sess.TOTAL_TURNS.startswith("claude.session.")
        assert sess.TOTAL_COST_USD.startswith("claude.session.")
        assert sess.TOTAL_INPUT_TOKENS.startswith("claude.session.")
        assert sess.TOTAL_OUTPUT_TOKENS.startswith("claude.session.")

    def test_turn_required_attrs(self) -> None:
        turn = TurnAttributes()
        assert turn.TURN_INDEX.startswith("claude.turn.")
        assert turn.MODEL.startswith("claude.turn.")
        assert turn.STOP_REASON.startswith("claude.turn.")
        assert turn.INPUT_TOKENS.startswith("claude.turn.")
        assert turn.OUTPUT_TOKENS.startswith("claude.turn.")
        assert turn.LATENCY_MS.startswith("claude.turn.")

    def test_tool_required_attrs(self) -> None:
        tool = ToolAttributes()
        assert tool.TOOL_USE_ID.startswith("claude.tool.")
        assert tool.TOOL_NAME.startswith("claude.tool.")
        assert tool.STATUS.startswith("claude.tool.")
        assert tool.LATENCY_MS.startswith("claude.tool.")
        assert tool.TURN_INDEX.startswith("claude.tool.")

    def test_cost_required_attrs(self) -> None:
        cost = CostAttributes()
        assert cost.INPUT_COST_USD.startswith("claude.cost.")
        assert cost.OUTPUT_COST_USD.startswith("claude.cost.")
        assert cost.TOTAL_COST_USD.startswith("claude.cost.")
        assert cost.MODEL.startswith("claude.cost.")


class TestFrozenInstances:
    """Verify that attribute dataclasses are immutable."""

    @pytest.mark.parametrize(
        "attr_class",
        [SessionAttributes, TurnAttributes, ToolAttributes, CostAttributes],
    )
    def test_frozen_dataclass(self, attr_class: Any) -> None:
        instance = attr_class()
        with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            instance.SESSION_ID = "mutated"  # type: ignore[misc]


class TestCategoryPrefixes:
    """Verify each category uses a distinct and correct prefix."""

    def test_session_prefix(self) -> None:
        values = _get_attr_values(SessionAttributes)
        for v in values:
            assert v.startswith("claude.session."), v

    def test_turn_prefix(self) -> None:
        values = _get_attr_values(TurnAttributes)
        for v in values:
            assert v.startswith("claude.turn."), v

    def test_tool_prefix(self) -> None:
        values = _get_attr_values(ToolAttributes)
        for v in values:
            assert v.startswith("claude.tool."), v

    def test_cost_prefix(self) -> None:
        values = _get_attr_values(CostAttributes)
        for v in values:
            assert v.startswith("claude.cost."), v


class TestAttributeCounts:
    """Smoke test: each category has a reasonable number of attributes."""

    def test_session_attribute_count(self) -> None:
        values = _get_attr_values(SessionAttributes)
        assert len(values) >= 10, f"Expected at least 10 session attributes, got {len(values)}"

    def test_turn_attribute_count(self) -> None:
        values = _get_attr_values(TurnAttributes)
        assert len(values) >= 10, f"Expected at least 10 turn attributes, got {len(values)}"

    def test_tool_attribute_count(self) -> None:
        values = _get_attr_values(ToolAttributes)
        assert len(values) >= 8, f"Expected at least 8 tool attributes, got {len(values)}"

    def test_cost_attribute_count(self) -> None:
        values = _get_attr_values(CostAttributes)
        assert len(values) >= 5, f"Expected at least 5 cost attributes, got {len(values)}"
