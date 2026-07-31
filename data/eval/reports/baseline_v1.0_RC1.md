# AI Meeting Analysis Baseline v1.0 RC1

- Model: Not evaluated in this placeholder report
- Prompt Version: Not evaluated in this placeholder report
- RAG Version: Not evaluated in this placeholder report

## Metrics Result

| Metric | Value |
| --- | ---: |
| Decision Precision | N/A |
| Task Recall | N/A |
| Risk Recall | N/A |
| Hallucination Rate | N/A |
| Evidence Coverage | N/A |

No production baseline has been generated from real `expected.json` and
`actual.json` files yet.

Generate the baseline with:

```powershell
python scripts\evaluate_meeting_analysis.py expected.json actual.json --transcript transcript.txt --output data\eval\reports\baseline_v1.0_RC1.md
```

The evaluator is offline-only and does not call Qwen3, Ollama, RAG, API,
database, Worker, ASR, semantic pipeline, or Mobile.
