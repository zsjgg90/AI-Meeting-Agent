import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings


class AgentConfigTest(unittest.TestCase):
    def test_agent_rollout_flags_default_to_rc_safe_values(self) -> None:
        settings = Settings()

        self.assertFalse(settings.agent_mode_enabled)
        self.assertTrue(settings.agent_shadow_mode)
        self.assertFalse(settings.agent_actions_enabled)
        self.assertFalse(settings.agent_command_execution_enabled)
        self.assertTrue(settings.agent_command_dry_run_only)

    def test_agent_rollout_flags_can_be_overridden(self) -> None:
        settings = Settings(
            agent_mode_enabled=True,
            agent_shadow_mode=False,
            agent_actions_enabled=True,
            agent_command_execution_enabled=True,
            agent_command_dry_run_only=False,
        )

        self.assertTrue(settings.agent_mode_enabled)
        self.assertFalse(settings.agent_shadow_mode)
        self.assertTrue(settings.agent_actions_enabled)
        self.assertTrue(settings.agent_command_execution_enabled)
        self.assertFalse(settings.agent_command_dry_run_only)


if __name__ == "__main__":
    unittest.main()
