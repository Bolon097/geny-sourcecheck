# GEN Y SourceCheck

SourceCheck is a local Python prototype for checking source signals in AI-generated research responses. It is designed as a supporting artifact for the GEN Y dissertation project, not as a fully integrated online feature of the main portal.

## Relationship to the GEN Y portal

The portal should link to SourceCheck as a separate local tool. At this stage, SourceCheck is best presented as a deployable prototype that can be demonstrated locally. A future version could connect it to the portal through one of three routes:

- plugin integration inside the project portal;
- server backend integration, where the portal calls a hosted API;
- fuller web integration with authentication, job history, and persistent results.

Keeping SourceCheck separate avoids over-claiming that the portal already contains a complete source-checking product.

## What SourceCheck checks

SourceCheck checks two levels only:

1. Level 1: whether an AI response contains source signals, including explicit links, DOI references, bare domains, named sources, platform/app/mini-program names, and source-related wording.
2. Level 2: whether a conservative machine-checkable source subset can be reached from the user's own computer through the local Python backend. This subset is limited to explicit HTTP URLs, explicit HTTPS URLs, and DOI references normalised to `https://doi.org/...`.

Level 3 claim-support verification is not implemented. That would require checking whether each source actually supports the specific claims, numbers, and meanings in the AI response.

SourceCheck does not judge whether an AI answer is factually correct. It only checks source presence and machine-checkable link accessibility.

## Level 2 checking scope

This prototype only performs automatic accessibility checks for:

- explicit `http://` URLs;
- explicit `https://` URLs;
- DOI references, normalised to `https://doi.org/...`.

Bare domains, `www` links without protocol, source names, report names, platform names, app names, mini-program names, malformed references, and incomplete references are recorded only as Level 1 signals or manual-review items. They are not automatically opened or counted as checked sources.

This conservative scope reduces unnecessary web requests, avoids guessing URLs from incomplete source names, and prevents the tool from presenting guessed domain checks as reliable verification.

## Privacy

Pasted AI responses are sent only to the local backend at `127.0.0.1:8000`. They are not sent to the project author, OpenAI, or any other LLM API. During Level 2 checks, the user's own computer requests only explicit HTTP URLs, explicit HTTPS URLs and DOI resolver pages.

## Recommended GitHub Repository Layout

```text
README.md
run_sourcecheck_mac.sh
run_sourcecheck_windows.bat
sourcecheck_backend/
  README.md
  requirements.txt
  source_verifier.py
  sourcecheck_api.py
  test_source_verifier.py
tools/
  extract_model_sources.py
```

`sourcecheck_backend/` contains the local FastAPI checker. `tools/extract_model_sources.py` is a helper script for extracting and deduplicating source references from the GEN Y comparison dashboard.

## Local Install

Manual setup:

```bash
cd sourcecheck_backend
python3 -m pip install -r requirements.txt
```

Mac/Linux shortcut:

```bash
./run_sourcecheck_mac.sh
```

Windows shortcut:

```bat
run_sourcecheck_windows.bat
```

The shortcut scripts create `sourcecheck_backend/.venv` if needed, install dependencies there, and run the backend on `127.0.0.1:8000`.

## Start the Backend Manually

```bash
cd sourcecheck_backend
uvicorn sourcecheck_api:app --host 127.0.0.1 --port 8000 --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/api/sourcecheck/health
```

## API Endpoints

- `GET /api/sourcecheck/health`
- `POST /api/sourcecheck/single`
- `POST /api/sourcecheck/batch`

Example batch request:

```bash
curl -X POST http://127.0.0.1:8000/api/sourcecheck/batch \
  -H "Content-Type: application/json" \
  -d '{"items":[{"item_id":"SQ1-GPT","response":"Source: https://www.iea.org/reports/global-ev-outlook-2024"}]}'
```

## Run Tests

```bash
cd sourcecheck_backend
python3 -m unittest test_source_verifier.py
```

## Manual Test Cases

Test 1: `Source: (data.hangzhou.gov.cn)`

- Expected: extract `data.hangzhou.gov.cn`
- Expected source type: `bare_domain`
- Expected Level 1: passed
- Expected Level 2: not machine checked
- Expected reason: Level 2 only checks explicit HTTP/HTTPS URLs and DOI references in this prototype.

Test 2: `Source: www.example.com`

- Expected: extract `www.example.com`
- Expected source type: `bare_domain`
- Expected Level 1: passed
- Expected Level 2: not machine checked
- Expected: do not normalise to `https://www.example.com`

Test 3: `Data from （data.zjzwfw.gov.cn）`

- Expected: extract `data.zjzwfw.gov.cn`
- Expected: strip Chinese brackets
- Expected source type: `bare_domain`

Test 4: `See https://www.iea.org/reports/global-ev-outlook-2024`

- Expected: extract full URL
- Expected source type: `url`
- Expected Level 2: machine-checkable

Test 5: `See http://example.com/report`

- Expected: extract full URL
- Expected source type: `url`
- Expected Level 2: machine-checkable

Test 6: `doi:10.1016/j.apenergy.2023.xxxxxx`

- Expected: extract DOI
- Expected normalized source: `https://doi.org/10.1016/j.apenergy.2023.xxxxxx`
- Expected source type: `doi`
- Expected Level 2: machine checked

Test 7: `According to government data, EV charging demand is increasing.`

- Expected Level 1: passed because source-related text exists
- Expected source type: `source_wording`
- Expected text-only source reference: `true`
- Expected Level 2: not machine checked

Test 8: `This is a model answer with no citation.`

- Expected Level 1: failed
- Expected source count: `0`

Test 9: `链接：(zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn)`

- Expected: extract the full bare domain
- Expected: strip brackets
- Expected Level 2: not machine checked
