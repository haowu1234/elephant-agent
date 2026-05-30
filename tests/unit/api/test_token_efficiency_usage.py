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

    def test_canonical_usage_prefers_final_ledger_step_for_same_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            database_path = Path(tempdir) / "usage.sqlite3"
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


if __name__ == "__main__":
    unittest.main()
