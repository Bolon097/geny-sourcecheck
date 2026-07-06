# SourceCheck Backend

Local FastAPI backend for the GEN Y SourceCheck prototype. This backend is intended for local dissertation demonstration and development, not as a hosted production service.

Run from this folder:

```bash
pip install -r requirements.txt
uvicorn sourcecheck_api:app --host 127.0.0.1 --port 8000 --reload
```

The project-level `run_sourcecheck_mac.sh` and `run_sourcecheck_windows.bat` scripts create and use `sourcecheck_backend/.venv` automatically.

API endpoints:

- `POST /api/sourcecheck/single`
- `POST /api/sourcecheck/batch`
- `GET /api/sourcecheck/health`

The backend performs Level 1 source-signal extraction and conservative Level 2 accessibility checks. Level 1 can record explicit links, DOI references, bare domains, named sources, platform/app/mini-program names, and source-related wording. Level 2 sends network requests only for explicit `http://` URLs, explicit `https://` URLs and DOI references normalised to `https://doi.org/...`.

Bare domains, `www` links without protocol, source names, report names, platform names, app names, mini-program names, malformed references and incomplete references may still be recorded as Level 1 source signals, but they are not automatically checked. They are marked `not_machine_checked_level1_signal` when Level 2 runs. The backend has no Level 3 claim-support verification and does not verify whether a source supports a claim.

For GitHub publication, include this folder alongside the root `README.md`, the two startup scripts, and `tools/extract_model_sources.py`.
