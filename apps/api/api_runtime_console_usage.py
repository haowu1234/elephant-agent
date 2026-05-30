"""Token usage helpers for dashboard operations."""

from __future__ import annotations

from collections.abc import Mapping
import json
import sqlite3
from typing import Any

from packages.telemetry import parse_token_efficiency_payload


def _json_loads(value: object, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _query(
    connection: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...] = (),
) -> list[dict[str, Any]]:
    try:
        rows = connection.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _int_value(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _cache_hit_rate_label(cached_tokens: int, prompt_tokens: int) -> str:
    if prompt_tokens <= 0:
        return "n/a"
    return f"{(cached_tokens / prompt_tokens) * 100:.1f}%"


def _cache_summary(*, cached_tokens: int, prompt_tokens: int, creation_tokens: int) -> str:
    if prompt_tokens <= 0:
        return "No input token usage recorded for this query."
    label = _cache_hit_rate_label(cached_tokens, prompt_tokens)
    creation_note = f"; {creation_tokens} cache-write token(s)" if creation_tokens else ""
    return f"{label} cache hit ({cached_tokens}/{prompt_tokens} input token(s) cached{creation_note})."


def normalize_token_usage_row(row: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(row)
    metadata_payload = _json_loads(record.pop("metadata_json", None), {})
    metadata = dict(metadata_payload) if isinstance(metadata_payload, Mapping) else {}
    ledger = parse_token_efficiency_payload(metadata.get("token_efficiency_json"))
    prompt_tokens = _int_value(record.get("prompt_tokens"))
    cached_tokens = _int_value(
        ledger.get("cachedInputTokens")
        or metadata.get("cached_prompt_tokens")
        or metadata.get("cachedPromptTokens")
        or metadata.get("cache_read_input_tokens")
    )
    creation_tokens = _int_value(
        ledger.get("cacheWriteInvestmentTokens")
        or metadata.get("cache_creation_prompt_tokens")
        or metadata.get("cacheCreationPromptTokens")
        or metadata.get("cache_creation_input_tokens")
    )
    cache_usage_reported = bool(
        ledger.get("cacheUsageReported")
        or _bool_value(metadata.get("cache_usage_reported"))
        or _bool_value(metadata.get("cacheUsageReported"))
        or "cached_prompt_tokens" in metadata
        or "cachedPromptTokens" in metadata
        or "cache_read_input_tokens" in metadata
        or "cache_creation_prompt_tokens" in metadata
        or "cacheCreationPromptTokens" in metadata
        or "cache_creation_input_tokens" in metadata
    )
    record["metadata"] = metadata
    if ledger:
        record["token_efficiency"] = ledger
        record["tokenEfficiency"] = ledger
        record["context_pressure_tokens"] = _int_value(
            ledger.get("contextPressureTokens") or metadata.get("context_pressure_tokens")
        )
        record["cost_pressure_tokens"] = _int_value(
            ledger.get("costPressureTokens") or metadata.get("cost_pressure_tokens")
        )
        record["non_cached_input_tokens"] = _int_value(
            ledger.get("nonCachedInputTokens") or metadata.get("non_cached_input_tokens")
        )
        record["cache_write_investment_tokens"] = _int_value(
            ledger.get("cacheWriteInvestmentTokens") or metadata.get("cache_write_investment_tokens")
        )
        record["contextPressureTokens"] = record["context_pressure_tokens"]
        record["costPressureTokens"] = record["cost_pressure_tokens"]
        record["nonCachedInputTokens"] = record["non_cached_input_tokens"]
        record["cacheWriteInvestmentTokens"] = record["cache_write_investment_tokens"]
        if ledger.get("contextPressureRatio") is not None:
            record["context_pressure_ratio"] = ledger.get("contextPressureRatio")
            record["contextPressureRatio"] = ledger.get("contextPressureRatio")
        if ledger.get("pressureSource"):
            record["pressure_source"] = ledger.get("pressureSource")
            record["pressureSource"] = ledger.get("pressureSource")
    record["cached_prompt_tokens"] = cached_tokens
    record["cache_creation_prompt_tokens"] = creation_tokens
    record["cache_usage_reported"] = cache_usage_reported
    record["cachedPromptTokens"] = cached_tokens
    record["cacheCreationPromptTokens"] = creation_tokens
    record["cacheUsageReported"] = cache_usage_reported
    if cache_usage_reported:
        cache_hit_rate_label = _cache_hit_rate_label(cached_tokens, prompt_tokens)
        cache_summary = _cache_summary(
            cached_tokens=cached_tokens,
            prompt_tokens=prompt_tokens,
            creation_tokens=creation_tokens,
        )
    else:
        cache_hit_rate_label = "n/a"
        cache_summary = "Cache usage was not reported by the provider for this query."
    record["cache_hit_rate_label"] = cache_hit_rate_label
    record["cache_summary"] = cache_summary
    record["cacheHitRateLabel"] = cache_hit_rate_label
    record["cacheSummary"] = cache_summary
    if cache_usage_reported and prompt_tokens > 0:
        cache_hit_rate = round(cached_tokens / prompt_tokens, 4)
        record["cache_hit_rate"] = cache_hit_rate
        record["cacheHitRate"] = cache_hit_rate
    return record


def token_efficiency_projection(events: list[dict[str, Any]]) -> dict[str, Any]:
    ledger_events = [event for event in events if isinstance(event.get("token_efficiency"), Mapping)]
    if not ledger_events:
        return {
            "summary": {
                "turns": 0,
                "episodes": 0,
                "contextPressureTokens": 0,
                "costPressureTokens": 0,
                "nonCachedInputTokens": 0,
                "cacheWriteInvestmentTokens": 0,
                "cacheHitRateLabel": "n/a",
            },
            "episodeTrajectories": (),
            "pressureSources": (),
            "compactionMarkers": (),
        }
    total_prompt = sum(_int_value(event.get("prompt_tokens")) for event in ledger_events)
    total_cached = sum(_int_value(event.get("cached_prompt_tokens")) for event in ledger_events)
    pressure_sources: dict[str, int] = {}
    compaction_markers: list[dict[str, Any]] = []
    by_episode: dict[str, list[dict[str, Any]]] = {}
    for event in ledger_events:
        ledger = event.get("token_efficiency")
        if not isinstance(ledger, Mapping):
            continue
        episode_id = str(ledger.get("episodeId") or event.get("session_id") or "unknown")
        by_episode.setdefault(episode_id, []).append(event)
        source = str(ledger.get("pressureSource") or event.get("pressure_source") or "unclassified")
        pressure_sources[source] = pressure_sources.get(source, 0) + _int_value(
            ledger.get("contextPressureTokens") or event.get("context_pressure_tokens")
        )
        compaction = ledger.get("compactionEvent")
        if isinstance(compaction, Mapping) and compaction:
            compaction_markers.append(
                {
                    "episodeId": episode_id,
                    "turnIndex": _int_value(ledger.get("turnIndex")),
                    "createdAt": ledger.get("createdAt") or event.get("created_at") or "",
                    "detail": compaction.get("detail") or "",
                    "reason": compaction.get("reason") or "",
                    "tokens": compaction.get("tokens") or "",
                }
            )
    trajectories = []
    for episode_id, rows in by_episode.items():
        sorted_rows = sorted(rows, key=lambda item: str(item.get("created_at") or ""))
        trajectory_rows = []
        for index, event in enumerate(sorted_rows, start=1):
            ledger = event.get("token_efficiency")
            if not isinstance(ledger, Mapping):
                continue
            buckets = ledger.get("buckets") if isinstance(ledger.get("buckets"), Mapping) else {}
            cache_hit = ledger.get("cacheHitRate")
            trajectory_rows.append(
                {
                    "turnIndex": _int_value(ledger.get("turnIndex")) or index,
                    "createdAt": ledger.get("createdAt") or event.get("created_at") or "",
                    "modelId": ledger.get("modelId") or event.get("model_id") or "",
                    "contextPressureTokens": _int_value(ledger.get("contextPressureTokens")),
                    "contextPressureRatio": _float_value(ledger.get("contextPressureRatio")),
                    "costPressureTokens": _int_value(ledger.get("costPressureTokens")),
                    "nonCachedInputTokens": _int_value(ledger.get("nonCachedInputTokens")),
                    "cacheWriteInvestmentTokens": _int_value(ledger.get("cacheWriteInvestmentTokens")),
                    "cacheHitRate": cache_hit if isinstance(cache_hit, (int, float)) else None,
                    "cacheHitRateLabel": (
                        f"{float(cache_hit) * 100:.1f}%"
                        if isinstance(cache_hit, (int, float))
                        else "n/a"
                    ),
                    "pressureSource": ledger.get("pressureSource") or "",
                    "buckets": dict(buckets),
                    "compactionEvent": dict(ledger.get("compactionEvent")) if isinstance(ledger.get("compactionEvent"), Mapping) else {},
                }
            )
        last_turn_at = trajectory_rows[-1]["createdAt"] if trajectory_rows else ""
        trajectories.append(
            {
                "episodeId": episode_id,
                "label": episode_id,
                "turns": len(trajectory_rows),
                "lastTurnAt": last_turn_at,
                "contextPressureTokens": sum(_int_value(row.get("contextPressureTokens")) for row in trajectory_rows),
                "costPressureTokens": sum(_int_value(row.get("costPressureTokens")) for row in trajectory_rows),
                "rows": tuple(trajectory_rows),
            }
        )
    return {
        "summary": {
            "turns": len(ledger_events),
            "episodes": len(by_episode),
            "contextPressureTokens": sum(_int_value(event.get("context_pressure_tokens")) for event in ledger_events),
            "costPressureTokens": sum(_int_value(event.get("cost_pressure_tokens")) for event in ledger_events),
            "nonCachedInputTokens": sum(_int_value(event.get("non_cached_input_tokens")) for event in ledger_events),
            "cacheWriteInvestmentTokens": sum(_int_value(event.get("cache_write_investment_tokens")) for event in ledger_events),
            "cacheHitRateLabel": _cache_hit_rate_label(total_cached, total_prompt) if total_prompt else "n/a",
            "cacheHitRate": round(total_cached / total_prompt, 4) if total_prompt else None,
        },
        "episodeTrajectories": tuple(
            sorted(trajectories, key=lambda item: str(item.get("lastTurnAt") or ""), reverse=True)[:50]
        ),
        "pressureSources": tuple(
            {"source": source, "contextPressureTokens": tokens}
            for source, tokens in sorted(pressure_sources.items(), key=lambda item: item[1], reverse=True)
        ),
        "compactionMarkers": tuple(compaction_markers),
    }


def token_usage_rows_for_session(connection: sqlite3.Connection, session_id: object) -> list[dict[str, Any]]:
    rows = _query(
        connection,
        """
        SELECT steps.step_id AS usage_id, steps.episode_id AS session_id,
               steps.personal_model_id AS profile_id, steps.loop_id AS run_id,
               steps.step_id AS source_event_id, steps.metadata_json,
               steps.created_at
        FROM steps
        WHERE steps.episode_id = ?
          AND (
            steps.metadata_json LIKE '%prompt_tokens%'
            OR steps.metadata_json LIKE '%completion_tokens%'
            OR steps.metadata_json LIKE '%total_tokens%'
          )
        ORDER BY steps.created_at ASC, steps.step_id ASC
        LIMIT 500
        """,
        (session_id,),
    )
    usage_rows: list[dict[str, Any]] = []
    for row in rows:
        metadata = _json_loads(row.get("metadata_json"), {})
        if not isinstance(metadata, Mapping):
            metadata = {}
        prompt_tokens = _int_value(metadata.get("prompt_tokens"))
        completion_tokens = _int_value(metadata.get("completion_tokens"))
        total_tokens = _int_value(metadata.get("total_tokens")) or prompt_tokens + completion_tokens
        if total_tokens <= 0:
            continue
        usage_rows.append(
            normalize_token_usage_row(
                {
                    **row,
                    "provider_id": metadata.get("provider_id") or metadata.get("providerId") or "runtime",
                    "model_id": metadata.get("model_id") or metadata.get("modelId") or "runtime-step",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "unit": "tokens",
                }
            )
        )
    return usage_rows


def summarize_token_usage(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    prompt_tokens = sum(_int_value(row.get("prompt_tokens")) for row in rows)
    completion_tokens = sum(_int_value(row.get("completion_tokens")) for row in rows)
    total_tokens = sum(_int_value(row.get("total_tokens")) for row in rows)
    cached_tokens = sum(_int_value(row.get("cached_prompt_tokens")) for row in rows)
    creation_tokens = sum(_int_value(row.get("cache_creation_prompt_tokens")) for row in rows)
    cache_usage_reported = any(bool(row.get("cache_usage_reported")) for row in rows)
    summary = {
        "promptTokens": prompt_tokens,
        "completionTokens": completion_tokens,
        "totalTokens": total_tokens,
        "cachedPromptTokens": cached_tokens,
        "cacheCreationPromptTokens": creation_tokens,
        "cacheUsageReported": cache_usage_reported,
        "cacheHitRateLabel": _cache_hit_rate_label(cached_tokens, prompt_tokens) if cache_usage_reported else "n/a",
        "cacheSummary": (
            _cache_summary(
                cached_tokens=cached_tokens,
                prompt_tokens=prompt_tokens,
                creation_tokens=creation_tokens,
            )
            if cache_usage_reported
            else "Cache usage was not reported by the provider for this query."
        ),
    }
    if cache_usage_reported and prompt_tokens > 0:
        summary["cacheHitRate"] = round(cached_tokens / prompt_tokens, 4)
    latest = rows[-1]
    if latest.get("provider_id"):
        summary["providerId"] = latest["provider_id"]
    if latest.get("model_id"):
        summary["modelId"] = latest["model_id"]
    return summary


def cache_usage_fields(run: Mapping[str, Any]) -> dict[str, Any]:
    token_usage = run.get("tokenUsage")
    if not isinstance(token_usage, Mapping):
        return {}
    if not token_usage.get("cacheUsageReported"):
        return {}
    cache_summary = str(token_usage.get("cacheSummary") or "").strip()
    if not cache_summary:
        return {}
    fields: dict[str, Any] = {
        "cacheHitRateLabel": token_usage.get("cacheHitRateLabel") or "n/a",
        "cacheSummary": cache_summary,
        "promptTokens": token_usage.get("promptTokens"),
        "cachedPromptTokens": token_usage.get("cachedPromptTokens"),
        "cacheCreationPromptTokens": token_usage.get("cacheCreationPromptTokens"),
    }
    if token_usage.get("cacheHitRate") is not None:
        fields["cacheHitRate"] = token_usage.get("cacheHitRate")
    return fields
