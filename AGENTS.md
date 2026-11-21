# AHA! (아하!) — Codex project instructions

## Goal
Build a working educational AI PoC for the Elice AI Challenge. Target: Korean high-school students who struggle with abstract concepts and need personalized, visual explanations grounded in their own study materials.

## Source of truth
1. `references/아하! v3.html`: teammate's existing landing-page design, interactive math and social-studies demos, and embedded video assets. Preserve its visual identity and working demos.
2. `references/아하! AI 학습 PoC.pdf`: 12-page pitch. Its page 7 user journey, pages 8–9 output modes, page 11 architecture, and page 12 PoC scope guide implementation.
3. `docs/PRODUCT_SPEC.md` and `docs/IMPLEMENTATION_PLAN.md`.

## Critical product constraints
- Two **independent** output paths: (A) generated interactive HTML; (B) generated 9:16 explanatory short video. A screen recording of path A is NOT path B.
- The core PoC scenario is Math II: secant slope converging to tangent slope for f(x)=x². Existing extra demos may remain, but do not expand scope before the core path works.
- User flow: upload study materials -> choose a difficult concept -> select learning format -> generate -> study.
- Generated content must be grounded in uploaded material where available; clearly identify assumptions or missing context.
- Do not claim an Elice video-generation API exists. Check actual Elice ML API documentation, authentication, quotas and model availability before integrating; use environment variables, never commit secrets.
- Treat LLM-generated HTML/JS as untrusted. Never inject it into the app's main DOM. Use an isolated sandboxed iframe with restrictive permissions and no same-origin privileges; validate outputs and limit execution resources. Do not promise complete security from iframe sandbox alone.
- Keep a deterministic local demo fallback so judges can try the product even if API calls fail.
- Never claim real-time generation, PDF parsing, TTS, MP4 export, or verification works until it is implemented and tested.

## Working style
- First inspect the existing HTML and repository before refactoring. The HTML is large and may contain embedded media; do not dump or rewrite it wholesale without need.
- Work in small, testable increments. Before each substantial change, explain files affected and acceptance criteria; after changes run relevant checks.
- Prefer FastAPI for backend and reuse existing vanilla HTML/CSS/JS for the first iteration; only introduce a frontend framework if clearly justified.
- Keep the original landing/demo functional and make new workflows additive.
- Document run commands, environment variables, API setup and fallback mode in README.
- No invented metrics, API endpoints, verified learning outcomes or test results.

## First assignment
Inspect `references/아하! v3.html`, review the two docs, propose a concrete repository layout, then implement phase 1: functional upload/question/format-selection UI and a FastAPI endpoint with a deterministic secant-to-tangent demo response. Do not implement external AI/video calls until phase 1 is working.
