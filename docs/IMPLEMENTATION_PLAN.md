# Implementation plan

## Current implementation status (2026-11-21)
- Phase 1: implemented; original landing, demos and video assets preserved.
- Phase 2: reuses PDF extraction, structured lesson specification, vetted rendering and fallback. Provider abstraction now supports fixed mock, real Gemini generateContent, and a network-free Elice placeholder. Validated output caching includes TTL/LRU and duplicate-request coalescing.
- Current requested model: `gemini-3.5-flash-lite`, selected via environment variables. Actual call status and any upstream failures are recorded honestly in `PHASE2_NOTES.md`; HTTP test doubles are never counted as successful real generation.
- Phase 3-A: separate generic storyboard DSL/API implemented with mock and Gemini HTTP-double tests. See `PHASE3A_NOTES.md` and `STORYBOARD_DSL.md`. Actual storyboard API calls, video rendering, TTS and MP4 storage have not been tested/implemented in this phase.
- Phase 3-B: local rendering engine/CLI with six HTML/SVG renderers, network-denied Playwright capture, macOS Korean TTS, FFmpeg encode/probe/decode, concurrency/time/disk limits and failure cleanup. See `PHASE3B_NOTES.md` for actual MP4 evidence. No rendering-job API or UI is added.
- Phase 3-C: implemented bounded single-runner web queue/API/UI, session ownership, Range streaming/download, acknowledged process cancellation, TTL/storage cleanup and reload recovery. See `PHASE3C_NOTES.md` for mock-AI/real-MP4 browser evidence. One server process; restart discards old web jobs/files.
- Phase 3-D checkpoint: three ChatKHU media providers/approval CLI passed HTTP-double tests. Approved image1/video1 generated and decoded (API-reported34.21/252credits); video playback passed. Unwanted arrows and hallucinated video labels fail direct educational use. TTS generation, multimodal scene integration and safe composition remain pending. See `PHASE3D_NOTES.md`.
- See `PHASE2_NOTES.md` and README for earlier real-call evidence, free-tier/age/data-use limitations and setup.

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

## Phase 2 — provider-based AI learning specifications
- Verify Gemini's official model, generateContent, structured output, terms and quota documentation. Use mock/gemini/elice provider implementations; keep Elice network calls unimplemented until the actual specifications are secured.
- Extract text from PDFs/images within bounded limits; OCR is optional, explicitly mark unsupported scanned files.
- Ask Gemini for structured lesson specification (concept, level, steps, graph parameters, examples, questions and source quotes), never executable code.
- Render with vetted component templates for the first PoC; if generating raw HTML/JS, run only in isolated sandbox with restrictive CSP and no same-origin privilege.
- Validate known math values; handle malformed model outputs and timeouts.
- Add bounded validated-output caching; include model, prompt/schema and exact input fingerprints. Coalesce duplicate concurrent inputs, never cache failures, and never log raw input or keys.
- Acceptance: an actual Gemini run, question/PDF context reflected in a validated lesson, working graph, cache reuse and graceful fallback. Report upstream failure status/messages when blocked; do not substitute HTTP fixtures for successful generation.

## Phase 3 — independent shorts pipeline
- Phase 3-A: `POST /api/storyboard`, StoryboardSpec, six allowlisted visualization types, timing/reference/source validation, separate prompt/schema/cache, and opt-in live-check script. Existing HTML/shorts API behavior is unchanged.
- Phase 3-B: independent synchronous local renderer consumes validated storyboards. 1080×1920 default, 540×960 preview, H.264/AAC, local Korean narration with explicit fit/error policy, disposable worker, no generated executable code.
- Phase 3-C: asynchronous `/api/videos` requests, real stage/frame progress, cancellation of worker/descendants, owned storage/export and UI integration. Memory-only job state; bounded retention and explicit restart policy.
- Phase 3-D: verify ChatKHU image/video/TTS independently before enabling media generation. Implemented providers + explicit test tools, approved image1/video1/TTS1, inspected assets, separate hashed scene-media plan, bounded FFmpeg composition and offline water-cycle A/B/C comparison. Media files are reviewed and reused; malformed/missing assets use SVG/local voice. Web paid-generation approval/UI remains outside this operator CLI integration. No automatic paid retry/fallback.
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
  app/providers/              # mock / gemini / unconnected elice
  app/services/cache.py
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
