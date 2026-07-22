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
        self.assertFalse(settings.agent_command_pilot_enabled)
        self.assertEqual(settings.command_pilot_tenant_set, set())
        self.assertEqual(settings.command_pilot_project_set, set())
        self.assertFalse(settings.agent_rollback_execution_enabled)
        self.assertFalse(settings.agent_global_kill_switch)
        self.assertFalse(settings.agent_grey_enabled)
        self.assertEqual(settings.agent_grey_tenant_set, set())
        self.assertEqual(settings.agent_grey_project_set, set())
        self.assertEqual(settings.agent_grey_user_set, set())
        self.assertEqual(settings.agent_grey_percentage, 0)
        self.assertEqual(settings.agent_grey_project_daily_limit, 0)
        self.assertEqual(settings.agent_grey_user_daily_limit, 0)
        self.assertEqual(settings.agent_grey_concurrency_limit, 0)
        self.assertFalse(settings.agent_grey_manual_paused)
        self.assertEqual(settings.agent_paused_tenant_set, set())
        self.assertEqual(settings.agent_paused_project_set, set())
        self.assertEqual(settings.agent_circuit_consecutive_failures, 0)
        self.assertEqual(settings.agent_circuit_version_conflict_rate, 0.0)
        self.assertEqual(settings.agent_circuit_rollback_failures, 0)

    def test_agent_rollout_flags_can_be_overridden(self) -> None:
        settings = Settings(
            agent_mode_enabled=True,
            agent_shadow_mode=False,
            agent_actions_enabled=True,
            agent_command_execution_enabled=True,
            agent_command_dry_run_only=False,
            agent_command_pilot_enabled=True,
            agent_command_pilot_tenants="tenant-1, tenant-2",
            agent_command_pilot_projects="project-1, project-2",
            agent_rollback_execution_enabled=True,
            agent_global_kill_switch=True,
            agent_grey_enabled=True,
            agent_grey_tenants="tenant-1, tenant-2",
            agent_grey_projects="project-1, project-2",
            agent_grey_users="user-1, user-2",
            agent_grey_percentage=50,
            agent_grey_project_daily_limit=10,
            agent_grey_user_daily_limit=3,
            agent_grey_concurrency_limit=1,
            agent_grey_manual_paused=True,
            agent_paused_tenants="tenant-paused",
            agent_paused_projects="project-paused",
            agent_circuit_consecutive_failures=5,
            agent_circuit_version_conflict_rate=0.5,
            agent_circuit_rollback_failures=2,
        )

        self.assertTrue(settings.agent_mode_enabled)
        self.assertFalse(settings.agent_shadow_mode)
        self.assertTrue(settings.agent_actions_enabled)
        self.assertTrue(settings.agent_command_execution_enabled)
        self.assertFalse(settings.agent_command_dry_run_only)
        self.assertTrue(settings.agent_command_pilot_enabled)
        self.assertEqual(settings.command_pilot_tenant_set, {"tenant-1", "tenant-2"})
        self.assertEqual(settings.command_pilot_project_set, {"project-1", "project-2"})
        self.assertTrue(settings.agent_rollback_execution_enabled)
        self.assertTrue(settings.agent_global_kill_switch)
        self.assertTrue(settings.agent_grey_enabled)
        self.assertEqual(settings.agent_grey_tenant_set, {"tenant-1", "tenant-2"})
        self.assertEqual(settings.agent_grey_project_set, {"project-1", "project-2"})
        self.assertEqual(settings.agent_grey_user_set, {"user-1", "user-2"})
        self.assertEqual(settings.agent_grey_percentage, 50)
        self.assertEqual(settings.agent_grey_project_daily_limit, 10)
        self.assertEqual(settings.agent_grey_user_daily_limit, 3)
        self.assertEqual(settings.agent_grey_concurrency_limit, 1)
        self.assertTrue(settings.agent_grey_manual_paused)
        self.assertEqual(settings.agent_paused_tenant_set, {"tenant-paused"})
        self.assertEqual(settings.agent_paused_project_set, {"project-paused"})
        self.assertEqual(settings.agent_circuit_consecutive_failures, 5)
        self.assertEqual(settings.agent_circuit_version_conflict_rate, 0.5)
        self.assertEqual(settings.agent_circuit_rollback_failures, 2)


if __name__ == "__main__":
    unittest.main()
