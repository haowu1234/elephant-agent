from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.api.api_runtime_internal_methods import _dashboard_step_row
from packages.contracts.layers import Step


class InternalDashboardStepRowsTest(unittest.TestCase):
    def test_tool_execute_detail_includes_exact_tool_result(self) -> None:
        step = Step(
            step_id="step:tool",
            loop_id="loop:test",
            episode_id="episode:test",
            state_id="state:test",
            personal_model_id="you",
            phase="acting",
            action="call_tool",
            status="completed",
            sequence=1,
            created_at=datetime.now(timezone.utc),
            summary="tool.diary.list description should not be the result",
            metadata={
                "tool_name": "tool.diary.list",
                "tool_arguments": '{"limit":5}',
                "tool_result": '{"entries":[],"count":0}',
                "execution_id": "exec:tool",
            },
        )

        row = _dashboard_step_row(step, {})

        self.assertEqual(row["event_type"], "tool_execute")
        self.assertEqual(row["content"], '{"entries":[],"count":0}')
        self.assertEqual(row["detail"]["tool_name"], "tool.diary.list")
        self.assertEqual(row["detail"]["tool_arguments"], '{"limit":5}')
        self.assertEqual(row["detail"]["tool_result"], '{"entries":[],"count":0}')

    def test_tool_execute_detail_truncates_large_dashboard_payloads(self) -> None:
        large_arguments = '{"command":"' + ('x' * 5_200) + '"}'
        large_result = 'y' * 9_200
        step = Step(
            step_id="step:tool-large",
            loop_id="loop:test",
            episode_id="episode:test",
            state_id="state:test",
            personal_model_id="you",
            phase="acting",
            action="call_tool",
            status="completed",
            sequence=2,
            created_at=datetime.now(timezone.utc),
            summary="large tool result",
            metadata={
                "tool_name": "tool.terminal.exec",
                "tool_arguments": large_arguments,
                "tool_result": large_result,
                "execution_id": "exec:tool-large",
            },
        )

        row = _dashboard_step_row(step, {})

        self.assertIn("[truncated ", row["content"])
        self.assertIn("[truncated ", row["detail"]["tool_arguments"])
        self.assertIn("[truncated ", row["detail"]["tool_result"])
        self.assertLess(len(row["detail"]["tool_arguments"]), len(large_arguments))
        self.assertLess(len(row["detail"]["tool_result"]), len(large_result))

    def test_tool_execute_detail_includes_sandbox_trace_metadata(self) -> None:
        step = Step(
            step_id="step:sandbox",
            loop_id="loop:test",
            episode_id="episode:test",
            state_id="state:test",
            personal_model_id="you",
            phase="acting",
            action="call_tool",
            status="completed",
            sequence=2,
            created_at=datetime.now(timezone.utc),
            summary="sandbox write complete",
            metadata={
                "tool_name": "tool.file.write",
                "tool_arguments": '{"path":"demo.py"}',
                "tool_result": "path: /home/user/demo.py",
                "execution_id": "exec:sandbox",
                "sandbox_backend": "cloud",
                "sandbox_provider": "tencent",
                "sandbox_backend_class": "TencentCloudBackend",
                "sandbox_id": "sbx-123",
                "sandbox_resolution": "reuse",
                "sandbox_cwd": "/home/user",
                "sandbox_template": "code-interpreter-v1",
                "sandbox_timeout_seconds": "3600",
                "sandbox_cached_session": "true",
            },
        )

        row = _dashboard_step_row(step, {})

        self.assertEqual(row["detail"]["sandbox_backend"], "cloud")
        self.assertEqual(row["detail"]["sandbox_provider"], "tencent")
        self.assertEqual(row["detail"]["sandbox_backend_class"], "TencentCloudBackend")
        self.assertEqual(row["detail"]["sandbox_id"], "sbx-123")
        self.assertEqual(row["detail"]["sandbox_resolution"], "reuse")
        self.assertEqual(row["detail"]["sandbox_cwd"], "/home/user")
        self.assertEqual(row["detail"]["sandbox_template"], "code-interpreter-v1")
        self.assertEqual(row["detail"]["sandbox_timeout_seconds"], "3600")
        self.assertEqual(row["detail"]["sandbox_cached_session"], "true")


if __name__ == "__main__":
    unittest.main()
