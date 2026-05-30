from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from apps.api.api_runtime_console_usage import normalize_token_usage_row, token_efficiency_projection
from apps.api.api_runtime_internal_methods import _canonical_usage
from packages.contracts import Episode, Loop, PersonalModel, State, Step
from packages.storage.repository_impl import RuntimeStorageRepository


def _bootstrap_usage_repository(database_path: Path) -> tuple[RuntimeStorageRepository, datetime]:
    repository = RuntimeStorageRepository(database_path)
    repository.bootstrap()
    now = datetime(2026, 5, 30, tzinfo=timezone.utc)
    repository.upsert_personal_model(
        PersonalModel(personal_model_id="profile-1", display_name="Ledger Demo", created_at=now, updated_at=now)
    )
    repository.upsert_state(
        State(
            state_id="state-1",
            personal_model_id="profile-1",
            state_anchor="elephant:ledger-demo",
            elephant_id="ledger-demo",
            elephant_name="Ledger Demo",
            created_at=now,
            updated_at=now,
        )
    )
    repository.upsert_episode(
        Episode(
            episode_id="episode-1",
            state_id="state-1",
            personal_model_id="profile-1",
            entry_surface="test",
            status="open",
            started_at=now,
            updated_at=now,
            elephant_id="ledger-demo",
        )
    )
    repository.upsert_loop(
        Loop(
            loop_id="loop-1",
            episode_id="episode-1",
            state_id="state-1",
            personal_model_id="profile-1",
            trigger_type="user_turn",
            status="completed",
            started_at=now,
            ended_at=now,
        )
    )
    return repository, now


class TokenEfficiencyUsageProjectionTest(unittest.TestCase):
    def test_normalized_usage_row_exposes_token_efficiency_fields(self) -> None:
        ledger = {
            "schemaVersion": "1",
            "episodeId": "episode-1",
            "turnIndex": 3,
            "createdAt": "2026-05-30T00:00:00+00:00",
            "promptTokens": 100,
            "completionTokens": 20,
            "contextPressureTokens": 100,
            "costPressureTokens": 50,
            "cachedInputTokens": 70,
            "nonCachedInputTokens": 30,
            "cacheWriteInvestmentTokens": 4,
            "cacheUsageReported": True,
            "cacheHitRate": 0.7,
            "pressureSource": "tool_result",
            "buckets": {"toolResultTokens": 60, "stablePrefixTokens": 20},
            "compactionEvent": {"reason": "usage", "tokens": "100->40"},
        }

        row = normalize_token_usage_row(
            {
                "usage_id": "step:1",
                "session_id": "episode-1",
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "metadata_json": json.dumps({"token_efficiency_schema": "1", "token_efficiency_json": ledger}),
            }
        )

        self.assertEqual(row["contextPressureTokens"], 100)
        self.assertEqual(row["costPressureTokens"], 50)
        self.assertEqual(row["nonCachedInputTokens"], 30)
        self.assertEqual(row["cacheWriteInvestmentTokens"], 4)
        self.assertEqual(row["cacheHitRateLabel"], "70.0%")
        self.assertEqual(row["pressureSource"], "tool_result")

    def test_projection_groups_rows_into_episode_trajectories(self) -> None:
        events = [
            normalize_token_usage_row(
                {
                    "usage_id": "step:1",
                    "session_id": "episode-1",
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "created_at": "2026-05-30T00:00:00+00:00",
                    "metadata_json": json.dumps(
                        {
                            "token_efficiency_schema": "1",
                            "token_efficiency_json": {
                                "schemaVersion": "1",
                                "episodeId": "episode-1",
                                "turnIndex": 1,
                                "createdAt": "2026-05-30T00:00:00+00:00",
                                "promptTokens": 100,
                                "completionTokens": 20,
                                "contextPressureTokens": 100,
                                "costPressureTokens": 50,
                                "cachedInputTokens": 70,
                                "nonCachedInputTokens": 30,
                                "cacheWriteInvestmentTokens": 4,
                                "cacheUsageReported": True,
                                "cacheHitRate": 0.7,
                                "pressureSource": "tool_result",
                                "buckets": {"toolResultTokens": 60},
                                "compactionEvent": {"reason": "usage", "tokens": "100->40"},
                            },
                        }
                    ),
                }
            )
        ]

        projection = token_efficiency_projection(events)

        self.assertEqual(projection["summary"]["turns"], 1)
        self.assertEqual(projection["summary"]["contextPressureTokens"], 100)
        self.assertEqual(projection["summary"]["costPressureTokens"], 50)
        self.assertEqual(projection["summary"]["cacheHitRateLabel"], "70.0%")
        self.assertEqual(projection["summary"]["episodes"], 1)
        self.assertEqual(projection["episodeTrajectories"][0]["episodeId"], "episode-1")
        self.assertEqual(projection["episodeTrajectories"][0]["rows"][0]["pressureSource"], "tool_result")
        self.assertEqual(projection["episodeTrajectories"][0]["rows"][0]["turnIndex"], 1)
        self.assertEqual(projection["compactionMarkers"][0]["tokens"], "100->40")

    def test_projection_falls_back_to_legacy_usage_rows(self) -> None:
        events = [
            normalize_token_usage_row(
                {
                    "usage_id": "step:legacy-1",
                    "session_id": "episode-1",
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "created_at": "2026-05-30T00:00:00+00:00",
                    "metadata_json": json.dumps(
                        {
                            "cached_prompt_tokens": "80",
                            "cache_usage_reported": "true",
                        }
                    ),
                }
            ),
            normalize_token_usage_row(
                {
                    "usage_id": "step:legacy-2",
                    "session_id": "episode-1",
                    "prompt_tokens": 200,
                    "completion_tokens": 10,
                    "total_tokens": 210,
                    "created_at": "2026-05-30T00:01:00+00:00",
                    "metadata_json": json.dumps({}),
                }
            ),
        ]

        projection = token_efficiency_projection(events)

        rows = projection["episodeTrajectories"][0]["rows"]
        self.assertEqual(projection["summary"]["turns"], 2)
        self.assertEqual(projection["summary"]["contextPressureTokens"], 300)
        self.assertEqual(projection["summary"]["costPressureTokens"], 250)
        self.assertEqual(projection["summary"]["cacheHitRateLabel"], "26.7%")
        self.assertEqual(projection["pressureSources"][0]["source"], "legacy_usage")
        self.assertEqual(rows[0]["turnIndex"], 1)
        self.assertEqual(rows[1]["turnIndex"], 2)
        self.assertEqual(rows[0]["pressureSource"], "legacy_usage")
        self.assertEqual(rows[0]["buckets"], {"unbucketedInputTokens": 100})
        self.assertEqual(rows[1]["contextPressureRatio"], 1.0)

    def test_canonical_usage_prefers_final_ledger_step_for_same_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = Path(tempdir) / "usage.sqlite3"
            repository, now = _bootstrap_usage_repository(database_path)
            repository.upsert_step(
                Step(
                    step_id="step:call-model",
                    loop_id="loop-1",
                    episode_id="episode-1",
                    state_id="state-1",
                    personal_model_id="profile-1",
                    phase="acting",
                    action="call_model",
                    status="completed",
                    sequence=1,
                    created_at=now,
                    metadata={
                        "execution_id": "execution-1",
                        "prompt_tokens": "100",
                        "completion_tokens": "20",
                        "total_tokens": "120",
                    },
                )
            )
            repository.upsert_step(
                Step(
                    step_id="step:emit-response",
                    loop_id="loop-1",
                    episode_id="episode-1",
                    state_id="state-1",
                    personal_model_id="profile-1",
                    phase="acting",
                    action="emit_response",
                    status="completed",
                    sequence=2,
                    created_at=now,
                    metadata={
                        "execution_id": "execution-1",
                        "prompt_tokens": "100",
                        "completion_tokens": "20",
                        "total_tokens": "120",
                        "token_efficiency_schema": "1",
                        "token_efficiency_json": json.dumps(
                            {
                                "schemaVersion": "1",
                                "episodeId": "episode-1",
                                "turnIndex": 1,
                                "createdAt": "2026-05-30T00:00:00+00:00",
                                "promptTokens": 100,
                                "completionTokens": 20,
                                "contextPressureTokens": 100,
                                "costPressureTokens": 50,
                                "cachedInputTokens": 70,
                                "nonCachedInputTokens": 30,
                                "cacheWriteInvestmentTokens": 4,
                                "cacheUsageReported": True,
                                "cacheHitRate": 0.7,
                                "pressureSource": "tool_result",
                                "buckets": {"toolResultTokens": 60},
                            }
                        ),
                    },
                )
            )

            usage = _canonical_usage(database_path)

        self.assertEqual(usage["summary"]["usageEvents"], 1)
        self.assertEqual(usage["summary"]["promptTokens"], 100)
        self.assertEqual(usage["tokenEvents"][0]["source_event_id"], "step:emit-response")
        self.assertEqual(usage["tokenEfficiency"]["summary"]["turns"], 1)
        self.assertEqual(usage["tokenEfficiency"]["summary"]["costPressureTokens"], 50)

    def test_canonical_usage_drops_legacy_loop_aggregate_emit_response(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = Path(tempdir) / "usage.sqlite3"
            repository, now = _bootstrap_usage_repository(database_path)
            repository.upsert_step(
                Step(
                    step_id="step:call-model-1",
                    loop_id="loop-1",
                    episode_id="episode-1",
                    state_id="state-1",
                    personal_model_id="profile-1",
                    phase="acting",
                    action="call_model",
                    status="completed",
                    sequence=1,
                    created_at=now,
                    metadata={
                        "execution_id": "execution-1",
                        "prompt_tokens": "60",
                        "completion_tokens": "6",
                        "total_tokens": "66",
                        "cached_prompt_tokens": "40",
                        "cache_usage_reported": "true",
                    },
                )
            )
            repository.upsert_step(
                Step(
                    step_id="step:call-model-2",
                    loop_id="loop-1",
                    episode_id="episode-1",
                    state_id="state-1",
                    personal_model_id="profile-1",
                    phase="acting",
                    action="call_model",
                    status="completed",
                    sequence=2,
                    created_at=now,
                    metadata={
                        "execution_id": "execution-2",
                        "prompt_tokens": "40",
                        "completion_tokens": "4",
                        "total_tokens": "44",
                        "cached_prompt_tokens": "20",
                        "cache_usage_reported": "true",
                    },
                )
            )
            repository.upsert_step(
                Step(
                    step_id="step:emit-response",
                    loop_id="loop-1",
                    episode_id="episode-1",
                    state_id="state-1",
                    personal_model_id="profile-1",
                    phase="acting",
                    action="emit_response",
                    status="completed",
                    sequence=3,
                    created_at=now,
                    metadata={
                        "prompt_tokens": "100",
                        "completion_tokens": "10",
                        "total_tokens": "110",
                        "cached_prompt_tokens": "0",
                        "cache_usage_reported": "true",
                    },
                )
            )

            usage = _canonical_usage(database_path)

        self.assertEqual(usage["summary"]["usageEvents"], 2)
        self.assertEqual(usage["summary"]["promptTokens"], 100)
        self.assertEqual(usage["summary"]["completionTokens"], 10)
        self.assertEqual(usage["summary"]["totalTokens"], 110)
        self.assertEqual({row["source_event_id"] for row in usage["tokenEvents"]}, {"step:call-model-1", "step:call-model-2"})
        self.assertEqual(usage["tokenEfficiency"]["summary"]["contextPressureTokens"], 100)
        self.assertEqual(usage["tokenEfficiency"]["summary"]["costPressureTokens"], 50)
        self.assertEqual(usage["tokenEfficiency"]["summary"]["cacheHitRateLabel"], "60.0%")
        self.assertEqual(usage["tokenEfficiency"]["episodeTrajectories"][0]["turns"], 2)

    def test_canonical_usage_keeps_ledger_loop_aggregate_for_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = Path(tempdir) / "usage.sqlite3"
            repository, now = _bootstrap_usage_repository(database_path)
            repository.upsert_step(
                Step(
                    step_id="step:call-model-1",
                    loop_id="loop-1",
                    episode_id="episode-1",
                    state_id="state-1",
                    personal_model_id="profile-1",
                    phase="acting",
                    action="call_model",
                    status="completed",
                    sequence=1,
                    created_at=now,
                    metadata={
                        "execution_id": "execution-1",
                        "prompt_tokens": "60",
                        "completion_tokens": "10",
                        "total_tokens": "70",
                    },
                )
            )
            repository.upsert_step(
                Step(
                    step_id="step:call-model-2",
                    loop_id="loop-1",
                    episode_id="episode-1",
                    state_id="state-1",
                    personal_model_id="profile-1",
                    phase="acting",
                    action="call_model",
                    status="completed",
                    sequence=2,
                    created_at=now,
                    metadata={
                        "execution_id": "execution-2",
                        "prompt_tokens": "30",
                        "completion_tokens": "20",
                        "total_tokens": "50",
                    },
                )
            )
            repository.upsert_step(
                Step(
                    step_id="step:emit-response",
                    loop_id="loop-1",
                    episode_id="episode-1",
                    state_id="state-1",
                    personal_model_id="profile-1",
                    phase="acting",
                    action="emit_response",
                    status="completed",
                    sequence=3,
                    created_at=now,
                    metadata={
                        "execution_id": "execution-2",
                        "prompt_tokens": "90",
                        "completion_tokens": "30",
                        "total_tokens": "120",
                        "token_efficiency_schema": "1",
                        "token_efficiency_json": json.dumps(
                            {
                                "schemaVersion": "1",
                                "episodeId": "episode-1",
                                "turnIndex": 7,
                                "createdAt": "2026-05-30T00:00:00+00:00",
                                "promptTokens": 90,
                                "completionTokens": 30,
                                "contextPressureTokens": 90,
                                "costPressureTokens": 50,
                                "cachedInputTokens": 70,
                                "nonCachedInputTokens": 20,
                                "cacheWriteInvestmentTokens": 4,
                                "cacheUsageReported": True,
                                "cacheHitRate": 0.7778,
                                "pressureSource": "runtime_summary",
                                "buckets": {"toolResultTokens": 30, "unbucketedInputTokens": 60},
                            }
                        ),
                    },
                )
            )

            usage = _canonical_usage(database_path)

        self.assertEqual(usage["summary"]["usageEvents"], 1)
        self.assertEqual(usage["summary"]["promptTokens"], 90)
        self.assertEqual(usage["summary"]["completionTokens"], 30)
        self.assertEqual(usage["summary"]["totalTokens"], 120)
        self.assertEqual(usage["tokenEvents"][0]["source_event_id"], "step:emit-response")
        self.assertEqual(usage["tokenEfficiency"]["summary"]["costPressureTokens"], 50)
        row = usage["tokenEfficiency"]["episodeTrajectories"][0]["rows"][0]
        self.assertEqual(row["turnIndex"], 1)
        self.assertEqual(row["sourceTurnIndex"], 7)
        self.assertEqual(row["buckets"], {"toolResultTokens": 30, "unbucketedInputTokens": 60})


if __name__ == "__main__":
    unittest.main()
