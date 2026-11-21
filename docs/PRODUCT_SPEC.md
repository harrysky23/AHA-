# AHA! Product specification (PoC)

## Problem and audience
A teacher addresses many students with different prior knowledge and comprehension speeds. Individually tailored re-explanations are hard to provide at scale. Target: Korean high-school students (grades 1–3), particularly those struggling with abstract mathematics and science concepts. Students may not know how to articulate where they are stuck.

## Core promise
Turn the student's study material and difficult concept into a personalized, visual learning experience rather than another generic chat answer.

## Primary user flow (pitch slide 7)
1. Upload study materials (PDF or images) and/or enter a question.
2. Select or type a difficult concept.
3. Choose an output mode: interactive HTML explanation or short video.
4. Generate and study the result. Enable follow-up questions and revisions as a future or stretch goal.

## Output A: interactive HTML (slides 6, 8, 11)
- Graphs, sliders and simulations that make concepts manipulable.
- Primary demo: f(x)=x²; manipulate Δx to see the secant approach the tangent, and display mathematically correct slope values.
- Formula for a=1: secant slope ((1+h)²-1)/h = 2+h (h≠0), tangent slope 2. Avoid division by zero.
- Phase 2 uses a provider abstraction: mock (fixed local demo), Gemini (structured lesson JSON), and an unconnected Elice implementation reserved for verified future specifications.
- Gemini's model ID is configured through environment variables. The current requested model is `gemini-3.5-flash-lite`; generated JSON passes strict schema, known-math and source-quote validation before vetted HTML/JS components render it.
- Gemini is currently for adult developer/judge local evaluation with synthetic/non-sensitive material. Its terms and free-tier data use must be considered before any service directed at minors; no public student-service eligibility is claimed.
- Run generated code in an isolated, constrained viewer; validate math and provide a review/quality checkpoint.

## Output B: independent learning short (slides 6, 9, 11)
- Phase 3-A implements only the independent storyboard JSON stage: generic concepts, a 30–60 second/9:16 scene specification and six allowlisted visualization types. It uses a separate schema, prompt and cache from the Math II HTML path.
- Phase 3-B adds a local synchronous renderer: vetted HTML/SVG components -> Playwright frames -> macOS Korean speech -> FFmpeg H.264/AAC MP4. Six visualization types, deterministic timeline, bounded worker execution and text fallback are implemented separately from the HTML lesson.
- Phase 3-C connects the independent pipeline to the existing web form through session-owned asynchronous `/api/videos` jobs: queue, actual stages, cancellation, protected Range streaming, playback/download and expiry. Gemini generation requires consent; ordinary verification uses mock storyboards and the real local renderer.
- `/api/learn` shorts still provides the existing sample video for compatibility; `/api/storyboard` returns JSON only. New web generation uses `/api/videos`. Job state is process-local, bounded, and discarded with web files on server restart. Browser reload recovery uses an opaque HttpOnly ownership cookie plus only the last job ID in localStorage.
- 9:16 vertical video, target 30–60 seconds.
- Pipeline: AI script/storyboard -> programmatic animation -> TTS -> FFmpeg encode/export.
- NOT a recording of the interactive HTML screen.
- No assumption of a dedicated Elice video API. Consider local deterministic animations and optional TTS providers; expose costs and dependencies before adding them.

## Visual design and existing prototype
Use the supplied `아하! v3.html` as the authoritative visual baseline. Preserve existing math and supply-demand interactive demos and their embedded media where possible. Add functional input/output screens without disrupting the existing landing experience.

## Scope and demo acceptance
Pitch slide 12 limits the initial PoC to one Math II secant→tangent scenario, two independent output-path concepts, basic sandboxing/verification plan and judge feedback. Implement a reliable, demonstrable path before adding general-purpose concept generation.

## Quality, safety and accuracy
- File type/size checks, safe extraction, clear user errors, API timeout and fallback.
- Math result checks for known scenarios; avoid claims that all arbitrary generated mathematics is verified.
- Never send sensitive study materials to an API without informing the user and using appropriate safeguards.
- Cache validated lesson specifications in bounded process-local TTL/LRU storage. Keys include provider, model, prompt/schema versions and exact input fingerprints; never log original questions, PDF text or credentials. Do not cache failures or count cache hits as new API/token usage.
- Do not imply copyright review is automated unless implemented.

## Pitch alignment
- Slide 2: classroom differentiation problem.
- Slide 5: students cannot describe where stuck and cannot find suitable explanations.
- Slides 6–7: dual learning modes and four-step user flow.
- Slide 8: secant-to-tangent interactive example.
- Slide 9: independently generated shorts.
- Slide 10: personalization/interaction versus chatbot and static videos.
- Slide 11: two technical pipelines and quality gates.
- Slide 12: initial PoC scope and future roadmap.
