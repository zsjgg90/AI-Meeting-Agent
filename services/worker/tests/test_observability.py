import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.observability import redact_sensitive_text, safe_value, text_digest


class ObservabilityTest(unittest.TestCase):
    def test_redacts_common_secrets(self) -> None:
        text = (
            "postgresql+psycopg://meeting_agent:meeting_agent@127.0.0.1:5432/meeting_agent "
            "Bearer abc.def.ghi api_key=sk-test-123 13812345678 user@example.com "
            "C:\\Users\\Administrator\\secret.txt"
        )

        redacted = redact_sensitive_text(text)

        self.assertNotIn("meeting_agent@127", redacted)
        self.assertNotIn("abc.def.ghi", redacted)
        self.assertNotIn("sk-test-123", redacted)
        self.assertNotIn("13812345678", redacted)
        self.assertNotIn("user@example.com", redacted)
        self.assertNotIn("Administrator", redacted)

    def test_content_fields_are_hashed_not_logged(self) -> None:
        value = safe_value("prompt", "会议原文和提示词内容")

        self.assertEqual(value["length"], len("会议原文和提示词内容"))
        self.assertEqual(value["sha256"], text_digest("会议原文和提示词内容"))
        self.assertNotIn("会议原文", str(value))

    def test_nested_values_are_sanitized(self) -> None:
        value = safe_value("payload", {"token": "abc", "items": ["13812345678"]})

        self.assertEqual(value["token"], "***")
        self.assertEqual(value["items"], ["1**********"])


if __name__ == "__main__":
    unittest.main()
