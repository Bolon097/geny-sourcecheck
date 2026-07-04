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

The backend only performs source presence extraction and link/domain/DOI accessibility checks. It does not verify whether a source supports a claim.

For GitHub publication, include this folder alongside the root `README.md`, the two startup scripts, and `tools/extract_model_sources.py`.
