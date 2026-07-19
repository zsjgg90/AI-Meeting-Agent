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

    def test_agent_rollout_flags_can_be_overridden(self) -> None:
        settings = Settings(
            agent_mode_enabled=True,
            agent_shadow_mode=False,
            agent_actions_enabled=True,
        )

        self.assertTrue(settings.agent_mode_enabled)
        self.assertFalse(settings.agent_shadow_mode)
        self.assertTrue(settings.agent_actions_enabled)


if __name__ == "__main__":
    unittest.main()
