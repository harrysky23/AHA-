# Implementation plan

## Phase 0 — repository inspection
- Inspect existing `아하! v3.html` DOM, CSS, scripts, tabs, links, embedded base64 assets and behavior.
- Confirm the landing page works before edits; identify insertion points for upload, concept input and format selection.
- Record baseline screenshots or manual verification notes.

## Phase 1 — fully clickable deterministic PoC
- FastAPI server serves the existing landing page and static assets.
- Input view: PDF/image picker, concept/question textarea, format selector (HTML vs shorts), generate button, loading/error states.
- Backend: `GET /api/health`, `POST /api/learn` (multipart form); validate input and return structured response.
- Start with one deterministic Math II example. Display an interactive graph and Δx slider using safe locally owned template code; do not pretend this is LLM-generated.
- Provide a demo short as a clearly labeled existing sample if present; do not imply new video generation.
- Acceptance: complete click-through works locally without paid API credentials; existing demos still work.

## Phase 2 — actual AI-backed HTML
- Verify Elice ML API documentation and credentials, model and rate limits; implement an adapter with `mock` and `elice` modes.
- Extract text from PDFs/images within bounded limits; OCR is optional, explicitly mark unsupported scanned files.
- Ask the model for structured lesson specification (concept, level, steps, graph parameters, questions) rather than unrestricted executable code where possible.
- Render with vetted component templates for the first PoC; if generating raw HTML/JS, run only in isolated sandbox with restrictive CSP and no same-origin privilege.
- Validate known math values; handle malformed model outputs and timeouts.
- Acceptance: at least one real Elice-backed run and graceful fallback, with logs proving mode used.

## Phase 3 — independent shorts pipeline
- Generate storyboard/script separately from HTML.
- Render vertical animation using programmatic motion graphics, add narration using a verified TTS service, encode with FFmpeg.
- Add background job handling, progress, export and failure fallback.
- Acceptance: newly generated 9:16 MP4 with synchronized narration; not a screen capture of path A. Measure latency and per-video cost.

## Phase 4 — polish and judging readiness
- Test on mobile and desktop, file upload errors, disconnected API, sandbox behavior and math correctness.
- Add demo reset, sample data, deployment docs, actual URL/QR for pitch slide 12.
- Provide honest architecture labels: implemented vs planned.

## Suggested repo structure
```
AGENTS.md
README.md
references/
  아하! v3.html
  아하! AI 학습 PoC.pdf
docs/
  PRODUCT_SPEC.md
  IMPLEMENTATION_PLAN.md
backend/
  app/main.py
  app/routes/learn.py
  app/services/elice.py
  app/services/lessons.py
  requirements.txt
frontend/
  index.html
  static/
tests/
```
Adapt structure to actual repository after inspection. Do not create empty architecture for its own sake.

## Suggested first Codex instruction
"Read AGENTS.md and both docs. Inspect the existing HTML before editing. Implement Phase 1 only: preserve landing and demos; add functional upload/concept/format-selection flow; wire it to FastAPI with a deterministic Math II secant-to-tangent lesson; document local run and tests. Do not call external AI or claim generated shorts yet."
