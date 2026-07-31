# Evaluation System

`data/eval` stores offline meeting-analysis evaluation assets. It is not part
of the production API, Worker, database, RAG, Prompt, ASR, semantic pipeline, or
mobile runtime.

Directory layout:

- `meeting_cases/`: curated case folders. Real transcripts and gold answers may
  be private; keep only sanitized fixtures under version control.
- `schema/`: JSON Schema contracts for evaluation inputs and outputs.
- `metrics/`: metric definitions and scoring notes.
- `reports/`: generated reports. Only the RC1 baseline report placeholder is
  tracked by default.

Run the offline evaluator:

```powershell
python scripts\evaluate_meeting_analysis.py expected.json actual.json --transcript transcript.txt --output data\eval\reports\baseline_v1.0_RC1.md
```

The evaluator compares already-produced JSON files. It never calls Qwen3,
Ollama, Chroma, PostgreSQL, API, Worker, or Expo.
