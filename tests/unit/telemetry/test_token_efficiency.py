from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from packages.telemetry import build_token_efficiency_record, token_efficiency_metadata


class TokenEfficiencyLedgerTest(unittest.TestCase):
    def test_cached_input_counts_for_context_but_not_cost_pressure(self) -> None:
        execution = SimpleNamespace(
            execution_id="exec-1",
            prompt_tokens=100,
            completion_tokens=30,
            total_tokens=130,
            cached_prompt_tokens=70,
            cache_creation_prompt_tokens=8,
            cache_usage_reported=True,
        )

        record = build_token_efficiency_record(
            context=SimpleNamespace(prompt_envelope=SimpleNamespace()),
            execution=execution,
            episode_id="episode-1",
            loop_id="loop-1",
            step_id="step-1",
            turn_index=1,
            created_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
            context_window_tokens=200,
        )

        self.assertEqual(record.context_pressure_tokens, 100)
        self.assertEqual(record.input_throughput_tokens, 100)
        self.assertEqual(record.peak_context_tokens, 100)
        self.assertEqual(record.last_context_tokens, 100)
        self.assertEqual(record.model_call_count, 1)
        self.assertEqual(record.non_cached_input_tokens, 30)
        self.assertEqual(record.cost_pressure_tokens, 60)
        self.assertEqual(record.cache_write_investment_tokens, 8)
        self.assertEqual(record.cache_hit_rate, 0.7)
        self.assertEqual(record.context_pressure_ratio, 0.5)
        self.assertEqual(record.context_pressure_quality, "aggregate_fallback")

    def test_peak_context_uses_largest_model_call_not_turn_throughput(self) -> None:
        execution = SimpleNamespace(
            execution_id="exec-1",
            prompt_tokens=300,
            completion_tokens=30,
            total_tokens=330,
            cached_prompt_tokens=210,
            cache_creation_prompt_tokens=0,
            cache_usage_reported=True,
        )
        model_call_steps = (
            SimpleNamespace(
                action="call_model",
                status="completed",
                metadata={
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "total_tokens": 110,
                    "cached_prompt_tokens": 70,
                },
            ),
            SimpleNamespace(
                action="call_model",
                status="completed",
                metadata={
                    "prompt_tokens": 200,
                    "completion_tokens": 20,
                    "total_tokens": 220,
                    "cached_prompt_tokens": 140,
                },
            ),
        )

        record = build_token_efficiency_record(
            context=SimpleNamespace(prompt_envelope=SimpleNamespace()),
            execution=execution,
            episode_id="episode-1",
            loop_id="loop-1",
            step_id="step-1",
            turn_index=1,
            created_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
            context_window_tokens=400,
            model_call_steps=model_call_steps,
        )

        self.assertEqual(record.prompt_tokens, 300)
        self.assertEqual(record.input_throughput_tokens, 300)
        self.assertEqual(record.context_pressure_tokens, 200)
        self.assertEqual(record.peak_context_tokens, 200)
        self.assertEqual(record.last_context_tokens, 200)
        self.assertEqual(record.model_call_count, 2)
        self.assertEqual(record.non_cached_input_tokens, 90)
        self.assertEqual(record.cost_pressure_tokens, 120)
        self.assertEqual(record.cache_hit_rate, 0.7)
        self.assertEqual(record.context_pressure_ratio, 0.5)
        self.assertEqual(record.context_pressure_kind, "peak_model_call_input")
        self.assertEqual(record.context_pressure_quality, "measured_model_calls")

    def test_metadata_carries_flat_fields_and_json_payload(self) -> None:
        execution = SimpleNamespace(
            execution_id="exec-2",
            prompt_tokens=40,
            completion_tokens=10,
            total_tokens=50,
            cached_prompt_tokens=0,
            cache_creation_prompt_tokens=0,
            cache_usage_reported=False,
        )

        record = build_token_efficiency_record(
            context=SimpleNamespace(prompt_envelope=SimpleNamespace()),
            execution=execution,
            episode_id="episode-2",
            loop_id="loop-2",
            step_id="step-2",
            turn_index=2,
            created_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
        )
        metadata = token_efficiency_metadata(record)

        self.assertEqual(metadata["token_efficiency_schema"], "2")
        self.assertEqual(metadata["context_pressure_tokens"], "40")
        self.assertEqual(metadata["cost_pressure_tokens"], "50")
        self.assertEqual(metadata["input_throughput_tokens"], "40")
        self.assertEqual(metadata["peak_context_tokens"], "40")
        self.assertEqual(metadata["model_call_count"], "1")
        self.assertIn('"contextPressureTokens":40', metadata["token_efficiency_json"])
        self.assertIn('"inputThroughputTokens":40', metadata["token_efficiency_json"])

    def test_turn_messages_do_not_double_count_current_user_or_final_assistant(self) -> None:
        execution = SimpleNamespace(
            execution_id="exec-3",
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            cached_prompt_tokens=0,
            cache_creation_prompt_tokens=0,
            cache_usage_reported=False,
        )
        context = SimpleNamespace(
            prompt_envelope=SimpleNamespace(
                frozen_prefix="stable prefix text",
                session_snapshot="resume packet",
                loop_context="current recall",
                messages=(SimpleNamespace(role="assistant", content="earlier reply"),),
            )
        )
        turn_messages = (
            SimpleNamespace(role="user", content="hello"),
            SimpleNamespace(role="tool", content="tool output"),
            SimpleNamespace(role="assistant", content="final answer"),
        )

        record = build_token_efficiency_record(
            context=context,
            execution=execution,
            episode_id="episode-3",
            loop_id="loop-3",
            step_id="step-3",
            turn_index=3,
            created_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
            user_prompt="hello",
            turn_messages=turn_messages,
        )

        self.assertGreater(record.buckets.current_user_input_tokens, 0)
        self.assertGreater(record.buckets.tool_result_tokens, 0)
        self.assertLess(record.buckets.message_history_tokens, record.prompt_tokens)


if __name__ == "__main__":
    unittest.main()
