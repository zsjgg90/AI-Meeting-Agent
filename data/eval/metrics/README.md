# Evaluation Metrics

Phase 0 metrics are deterministic text-match metrics for offline regression:

- Decision Precision: matched actual `key_conclusions` divided by actual
  `key_conclusions`.
- Task Recall: matched expected `action_items` divided by expected
  `action_items`.
- Risk Recall: matched expected `risks_and_focus` divided by expected
  `risks_and_focus`.
- Hallucination Rate: actual conclusion/action/issue/risk items without
  continuous transcript evidence divided by all actual conclusion/action/issue/
  risk items.
- Evidence Coverage: actual conclusion/action/issue/risk items with continuous
  transcript-backed `source_text` divided by all actual conclusion/action/issue/
  risk items.

Matching uses normalized exact/substring comparison across canonical
`meeting-analysis-v1` text fields. It is intentionally simple for Phase 0 and
should be treated as infrastructure, not final semantic scoring.
