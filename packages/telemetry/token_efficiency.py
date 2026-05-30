"""Token efficiency ledger helpers.

The ledger is an observational turn-level account: it explains prompt pressure,
cache economics, and coarse input buckets without becoming a runtime decision
engine.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from typing import Any


TOKEN_EFFICIENCY_SCHEMA_VERSION = "1"


@dataclass(frozen=True, slots=True)
class TokenEfficiencyBuckets:
    stable_prefix_tokens: int = 0
    session_snapshot_tokens: int = 0
    loop_context_tokens: int = 0
    message_history_tokens: int = 0
    tool_schema_tokens: int = 0
    tool_result_tokens: int = 0
    current_user_input_tokens: int = 0
    unbucketed_input_tokens: int = 0

    @property
    def bucketed_input_tokens(self) -> int:
        return sum(
            (
                self.stable_prefix_tokens,
                self.session_snapshot_tokens,
                self.loop_context_tokens,
                self.message_history_tokens,
                self.tool_schema_tokens,
                self.tool_result_tokens,
                self.current_user_input_tokens,
                self.unbucketed_input_tokens,
            )
        )


@dataclass(frozen=True, slots=True)
class TokenEfficiencyLedgerRecord:
    schema_version: str
    scope: str
    episode_id: str
    loop_id: str
    step_id: str
    execution_id: str
    turn_index: int
    created_at: str
    provider_id: str = ""
    model_id: str = ""
    transport_id: str = ""
    context_window_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_input_tokens: int = 0
    non_cached_input_tokens: int = 0
    cache_write_investment_tokens: int = 0
    cache_usage_reported: bool = False
    cache_hit_rate: float | None = None
    context_pressure_tokens: int = 0
    context_pressure_ratio: float | None = None
    cost_pressure_tokens: int = 0
    pressure_source: str = ""
    cache_break_reason: str = ""
    compaction_event: Mapping[str, object] = field(default_factory=dict)
    buckets: TokenEfficiencyBuckets = field(default_factory=TokenEfficiencyBuckets)


def build_token_efficiency_record(
    *,
    context: object,
    execution: object,
    episode_id: str,
    loop_id: str,
    step_id: str,
    turn_index: int,
    created_at: datetime,
    user_prompt: str = "",
    turn_messages: Sequence[object] = (),
    stages: Sequence[object] = (),
    provider_id: str = "",
    model_id: str = "",
    transport_id: str = "",
    context_window_tokens: int = 0,
) -> TokenEfficiencyLedgerRecord:
    prompt_tokens = _int_value(getattr(execution, "prompt_tokens", 0))
    completion_tokens = _int_value(getattr(execution, "completion_tokens", 0))
    total_tokens = _int_value(getattr(execution, "total_tokens", 0)) or prompt_tokens + completion_tokens
    cached_input_tokens = _int_value(getattr(execution, "cached_prompt_tokens", 0))
    cache_write_tokens = _int_value(getattr(execution, "cache_creation_prompt_tokens", 0))
    cache_usage_reported = bool(getattr(execution, "cache_usage_reported", False))
    non_cached_input_tokens = max(prompt_tokens - cached_input_tokens, 0)
    cache_hit_rate = (
        round(cached_input_tokens / prompt_tokens, 4)
        if cache_usage_reported and prompt_tokens > 0
        else None
    )
    context_pressure_ratio = (
        round(prompt_tokens / context_window_tokens, 4)
        if context_window_tokens > 0 and prompt_tokens > 0
        else None
    )
    buckets = _estimate_buckets(
        context=context,
        prompt_tokens=prompt_tokens,
        user_prompt=user_prompt,
        turn_messages=turn_messages,
    )
    return TokenEfficiencyLedgerRecord(
        schema_version=TOKEN_EFFICIENCY_SCHEMA_VERSION,
        scope="turn",
        episode_id=episode_id,
        loop_id=loop_id,
        step_id=step_id,
        execution_id=str(getattr(execution, "execution_id", "") or ""),
        turn_index=max(0, int(turn_index or 0)),
        created_at=created_at.isoformat(),
        provider_id=provider_id,
        model_id=model_id,
        transport_id=transport_id,
        context_window_tokens=context_window_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
        non_cached_input_tokens=non_cached_input_tokens,
        cache_write_investment_tokens=cache_write_tokens,
        cache_usage_reported=cache_usage_reported,
        cache_hit_rate=cache_hit_rate,
        context_pressure_tokens=prompt_tokens,
        context_pressure_ratio=context_pressure_ratio,
        cost_pressure_tokens=non_cached_input_tokens + completion_tokens,
        pressure_source=_pressure_source(buckets),
        compaction_event=_latest_compaction_event(stages),
        buckets=buckets,
    )


def token_efficiency_metadata(record: TokenEfficiencyLedgerRecord) -> dict[str, str]:
    payload = token_efficiency_payload(record)
    fields: dict[str, str] = {
        "token_efficiency_schema": record.schema_version,
        "context_pressure_tokens": str(record.context_pressure_tokens),
        "cost_pressure_tokens": str(record.cost_pressure_tokens),
        "non_cached_input_tokens": str(record.non_cached_input_tokens),
        "cache_write_investment_tokens": str(record.cache_write_investment_tokens),
        "token_efficiency_pressure_source": record.pressure_source,
        "token_efficiency_json": json.dumps(payload, separators=(",", ":"), sort_keys=True),
    }
    if record.cache_hit_rate is not None:
        fields["cache_hit_rate"] = f"{record.cache_hit_rate:.4f}"
    if record.context_pressure_ratio is not None:
        fields["context_pressure_ratio"] = f"{record.context_pressure_ratio:.4f}"
    return fields


def token_efficiency_payload(record: TokenEfficiencyLedgerRecord) -> dict[str, Any]:
    payload = _camelize_mapping(asdict(record))
    payload["buckets"]["bucketedInputTokens"] = record.buckets.bucketed_input_tokens
    return payload


def parse_token_efficiency_payload(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        payload = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _estimate_buckets(
    *,
    context: object,
    prompt_tokens: int,
    user_prompt: str,
    turn_messages: Sequence[object],
) -> TokenEfficiencyBuckets:
    envelope = getattr(context, "prompt_envelope", None)
    stable_prefix_tokens = _estimate_tokens(getattr(envelope, "frozen_prefix", "") if envelope else "")
    session_snapshot_tokens = _estimate_tokens(getattr(envelope, "session_snapshot", "") if envelope else "")
    loop_context_tokens = _estimate_tokens(getattr(envelope, "loop_context", "") if envelope else "")
    current_user_input_tokens = _estimate_tokens(user_prompt)
    message_history_tokens = 0
    tool_result_tokens = 0
    for message in tuple(getattr(envelope, "messages", ()) if envelope else ()):
        tokens = _estimate_message_tokens(message)
        if _is_tool_result_message(message):
            tool_result_tokens += tokens
        else:
            message_history_tokens += tokens
    for message in _input_relevant_turn_messages(turn_messages, user_prompt=user_prompt):
        tokens = _estimate_message_tokens(message)
        if _is_tool_result_message(message):
            tool_result_tokens += tokens
        else:
            message_history_tokens += tokens
    known = sum(
        (
            stable_prefix_tokens,
            session_snapshot_tokens,
            loop_context_tokens,
            message_history_tokens,
            tool_result_tokens,
            current_user_input_tokens,
        )
    )
    unbucketed = max(prompt_tokens - known, 0)
    return TokenEfficiencyBuckets(
        stable_prefix_tokens=stable_prefix_tokens,
        session_snapshot_tokens=session_snapshot_tokens,
        loop_context_tokens=loop_context_tokens,
        message_history_tokens=message_history_tokens,
        tool_result_tokens=tool_result_tokens,
        current_user_input_tokens=current_user_input_tokens,
        unbucketed_input_tokens=unbucketed,
    )


def _estimate_message_tokens(message: object) -> int:
    content = str(getattr(message, "content", "") or "")
    tool_name = str(getattr(message, "tool_name", "") or "")
    role = str(getattr(message, "role", "") or "")
    calls = getattr(message, "tool_calls", ()) or ()
    call_text = json.dumps(calls, separators=(",", ":"), sort_keys=True, default=str) if calls else ""
    return _estimate_tokens("\n".join(part for part in (role, tool_name, content, call_text) if part))


def _input_relevant_turn_messages(
    turn_messages: Sequence[object],
    *,
    user_prompt: str,
) -> tuple[object, ...]:
    messages = tuple(turn_messages or ())
    relevant: list[object] = []
    normalized_user_prompt = str(user_prompt or "").strip()
    for index, message in enumerate(messages):
        role = str(getattr(message, "role", "") or "").strip().lower()
        content = str(getattr(message, "content", "") or "").strip()
        calls = tuple(getattr(message, "tool_calls", ()) or ())
        if role == "user" and content == normalized_user_prompt:
            continue
        if index == len(messages) - 1 and role == "assistant" and not calls:
            continue
        relevant.append(message)
    return tuple(relevant)


def _estimate_tokens(text: object) -> int:
    value = str(text or "").strip()
    if not value:
        return 0
    try:
        from packages.context.projection import estimate_projection_tokens

        return max(0, int(estimate_projection_tokens(value)))
    except Exception:
        return max(1, (len(value) + 3) // 4)


def _is_tool_result_message(message: object) -> bool:
    role = str(getattr(message, "role", "") or "").strip().lower()
    return role in {"tool", "toolresult", "tool_result"} or bool(str(getattr(message, "tool_call_id", "") or ""))


def _pressure_source(buckets: TokenEfficiencyBuckets) -> str:
    candidates = {
        "stable_prefix": buckets.stable_prefix_tokens,
        "session_snapshot": buckets.session_snapshot_tokens,
        "loop_context": buckets.loop_context_tokens,
        "message_history": buckets.message_history_tokens,
        "tool_schema": buckets.tool_schema_tokens,
        "tool_result": buckets.tool_result_tokens,
        "current_user_input": buckets.current_user_input_tokens,
        "unbucketed": buckets.unbucketed_input_tokens,
    }
    source, value = max(candidates.items(), key=lambda item: item[1])
    return source if value > 0 else ""


def _latest_compaction_event(stages: Sequence[object]) -> dict[str, object]:
    for stage in reversed(tuple(stages or ())):
        if str(getattr(stage, "stage", "") or "") != "context-compact":
            continue
        detail = str(getattr(stage, "detail", "") or "")
        event: dict[str, object] = {"detail": detail}
        for segment in detail.split():
            if segment.startswith("reason="):
                event["reason"] = segment[len("reason="):]
            elif segment.startswith("tokens="):
                event["tokens"] = segment[len("tokens="):]
            elif segment.startswith("messages="):
                event["messages"] = segment[len("messages="):]
            elif segment.startswith("compacted_messages="):
                event["compactedMessages"] = _int_value(segment[len("compacted_messages="):])
        recorded_at = getattr(stage, "recorded_at", None)
        if recorded_at is not None:
            event["recordedAt"] = recorded_at.isoformat() if hasattr(recorded_at, "isoformat") else str(recorded_at)
        return event
    return {}


def _int_value(value: object) -> int:
    try:
        return max(0, int(str(value or "0")))
    except (TypeError, ValueError):
        return 0


def _camelize_mapping(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {_camelize_key(str(key)): _camelize_mapping(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camelize_mapping(item) for item in value]
    return value


def _camelize_key(value: str) -> str:
    parts = value.split("_")
    if not parts:
        return value
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
