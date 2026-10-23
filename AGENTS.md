# Repository Guidelines

## Reference Docs
- Codebase summary: see `SUMMARY.md` for a high-level overview (architecture, data flow, logging, configuration, workflows).
- Code map: see `CODEMAP.md` for a full tree and per-file index of key classes/functions.

## Project Structure & Module Organization
- `app.py`: FastAPI service combining YOLO detection and OCR (primary entry).
- `app_ocr.py`, `app_nice_version.py`: alternative/experimental API variants.
- `models/`: model helpers; `weights/`: YOLO weights (e.g., `weights/model.pt`).
- `index.html`, `drawing.js`: simple UI artifacts; not required for API use.
- `requirements.txt`: Python dependencies; `.env`: local configuration (ignored by Git).

## Build, Test, and Development Commands
- Create env: `python -m venv myenv && source myenv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Run API (dev): `uvicorn app:app --reload --host 0.0.0.0 --port 8000`
- Health check: `curl -s http://localhost:8000/health`
- Predict example: `curl -F image=@sample.png "http://localhost:8000/predict?return_image=false"`
- Optional: set weights via env: `export YOLO_WEIGHTS=weights/model.pt`

## Coding Style & Naming Conventions
- Language: Python 3.10+; 4‑space indentation; UTF‑8.
- Naming: files `snake_case.py`; functions/vars `snake_case`; classes `CamelCase`.
- Type hints and short docstrings for public functions; prefer small, pure helpers.
- FastAPI routes: explicit models via Pydantic; validate inputs; keep endpoints idempotent.

## Testing Guidelines
- Manual API checks via `curl` or HTTP clients against `/health` and `/predict`.
- Add focused tests under `tests/` using `pytest` if contributing new logic; name files `test_*.py`.
- Include minimal fixtures and sample images when relevant; avoid committing large binaries.

## Commit & Pull Request Guidelines
- Commits: short, imperative, lowercase subjects (e.g., `add endpoint doc`, `ocr added`).
- Scope changes narrowly; include rationale in body when non‑trivial.
- PRs must include: concise description, screenshots or JSON samples for API changes, steps to reproduce, and any config/env vars used (e.g., `YOLO_WEIGHTS`). Link related issues.

### Commit Discipline
- Commit every new feature or fix as soon as it’s complete (don’t defer commits).
- Keep commits atomic and focused; avoid bundling unrelated changes.
- Prefer small, frequent commits to aid code review and debugging.
- With every commit, update `SUMMARY.md` and `CODEMAP.md` to reflect changes (files added/removed, new functions/classes, updated flow or logging paths).

## Security & Configuration Tips
- Do not commit secrets or large weights; keep `.env` and `weights/` out of Git unless using small, public test assets.
- Configure runtime via env: `YOLO_WEIGHTS`, `YOLO_CONF`, `YOLO_IOU`, `YOLO_IMGSZ`.
- GPU: code auto‑detects Apple MPS; falls back to CPU. Set `device` via Torch envs if needed.
