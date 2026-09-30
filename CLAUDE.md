# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Install deps: `uv sync` (Python >=3.13; always use `uv`, never pip directly)
- Run the app: `./run.sh` (or `cd backend && uv run uvicorn app:app --reload --port 8000`). Web UI at `localhost:8000`, Swagger at `/docs`.
- Requires `ANTHROPIC_API_KEY` in a `.env` file (see `.env.example`).
- There are no tests and no linter configured. `main.py` at the repo root is an unused stub.

## Architecture

A RAG chatbot over course transcripts. FastAPI serves both the JSON API and the static `frontend/` (vanilla JS, no build step).

**The server must be run from `backend/`.** `app.py` loads docs from the relative path `../docs`, Chroma persists to `./chroma_db` (relative to `backend/`), and the backend modules use flat imports (`from models import ...`), not a package.

### Query flow (spans several files)
`frontend/script.js` → `POST /api/query` (`app.py`) → `RAGSystem.query` (`rag_system.py`) → `AIGenerator.generate_response` (`ai_generator.py`) → Claude.

- Retrieval is **tool-based, not always-on**. Claude decides whether to call the `search_course_content` tool (`search_tools.py`). General-knowledge questions skip retrieval entirely.
- `AIGenerator` makes up to two Claude calls. The first has tools enabled. If it returns `tool_use`, the tool runs and a **second call is made without tools**, so at most one search happens per query. The system prompt also enforces this.
- `CourseSearchTool` → `VectorStore.search` (`vector_store.py`). If a `course_name` is given, it is first resolved to a canonical title by embedding search in the `course_catalog` collection. Then `course_content` is queried with an optional `course_title`/`lesson_number` filter.
- Sources shown in the UI travel out-of-band. `CourseSearchTool.last_sources` is set during the tool call, and `RAGSystem.query` reads and resets it through `ToolManager`. This is shared mutable state on a singleton, so it is not safe for concurrent requests.
- Conversation history is an in-memory `SessionManager` dict. It is injected into the **system prompt as text**, not as message turns, and it is lost on restart. A missing `session_id` gets a new one, and the frontend stores the returned one.

### Ingestion
- On startup, `app.py` calls `add_course_folder("../docs")`. Courses whose title already exists in Chroma are skipped, so edits to an existing doc are **not** re-ingested unless the DB is cleared (delete `backend/chroma_db` or use `clear_existing=True`).
- Doc format expected by `DocumentProcessor`: line 1 `Course Title:`, then `Course Link:` and `Course Instructor:`, then `Lesson N: <title>` markers, each optionally followed by `Lesson Link:`. Text is split into sentence-aligned chunks (`CHUNK_SIZE=800`, `CHUNK_OVERLAP=100` characters).
- The course title is used as the Chroma document ID, so titles must be unique.

### Config
All tunables (model name, embedding model, chunk sizes, `MAX_RESULTS`, `MAX_HISTORY`) live in `backend/config.py`. The Claude call uses `temperature=0` and `max_tokens=800` (in `AIGenerator`).
