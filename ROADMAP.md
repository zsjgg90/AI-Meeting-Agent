# Roadmap

## Version 1.1

- Complete MeetMind Agent v1.0 Phase 0 baseline freeze with recorded Git branch,
  commit, and reusable 19-meeting acceptance dataset.
- Merge or generate shared API/Worker SQLAlchemy model definitions.
- Archive legacy root `api` and `mobile` directories.
- Add clean-database migration verification.
- Add a live Qwen3 + RAG benchmark gate outside default unit tests.
- Add end-to-end smoke test for recording, upload, processing, analysis, and display.

## Version 1.2

- Integrate Semantic Event extraction into the formal analysis pipeline.
- Expand meeting fixtures and benchmark datasets.
- Add speaker identity mapping workflow and review UI.
- Add export regression tests for Markdown, TXT, Word, and PDF.
- Improve offline packaging for RAG embedding models.

## Version 2.0

- Multi-agent orchestration with Recorder, Transcript, Speaker, Semantic, Summary, Action, Memory, and Orchestrator agents.
- Meeting knowledge graph and long-term memory.
- Enterprise permissions, workspace boundaries, and audit trails.
- Online collaboration and multi-device synchronization.
- MCP tool calling for downstream task systems and knowledge bases.
