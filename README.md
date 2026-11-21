# AHA! (아하!) · Phase 2 + Phase 3-A

기존 랜딩·수학·사회 데모를 유지하고 FastAPI에 **자료 업로드 → 질문 → 학습 방식 → JSON 학습 명세 → 인터랙티브 학습**을 연결했습니다.

HTML 학습의 지원 개념은 수학 II의 **f(x)=x², a=1에서 할선→접선·미분계수**입니다. AI는 설명·수준·예제·확인 문제를 JSON으로 만들고, 검증된 로컬 HTML/JS 컴포넌트가 그래프를 계산합니다. Phase 3-A는 별도의 범용 영상 스토리보드 JSON을 추가합니다. AI 코드 실행·MP4 렌더링·TTS·FFmpeg·영상 저장은 구현하지 않았습니다.

## 현재 Provider

| 값 | 동작 |
| --- | --- |
| `mock` | HTML은 고정 수학 II 예제, 스토리보드는 개념별 템플릿. 키·외부 호출 없이 작동 |
| `gemini` | Gemini Developer API의 실제 `generateContent` 호출. 질문·추출 텍스트로 JSON 명세 생성 |
| `elice` | 별도 준비 구현체. 실제 사양 확정 전에는 네트워크 호출 없이 연결 예정 오류 반환 |

기본 모델은 **`gemini-3.5-flash-lite`**이며 `GEMINI_MODEL`로 바꿀 수 있습니다. 실제 생성 2건과 FastAPI·PDF·그래프·캐시 재사용을 검증했습니다. 처음 지정했던 2.5 모델의 404와 3.5의 일시적 503도 기록했습니다. 상세 결과는 [Phase 2 기록](docs/PHASE2_NOTES.md)을 참조하세요. HTTP 대역 테스트는 실제 AI 생성 성공으로 계산하지 않습니다.

## Phase 3-A · 범용 스토리보드 JSON

`POST /api/storyboard`를 추가했습니다. 기존 `/api/learn`의 HTML·기존 영상 응답과 프론트엔드는 유지합니다. 새 API는 `StoryboardSpec(schema_version=storyboard-1)`을 반환하며 `LessonSpec`과 분리되어 있습니다. 이번 단계는 스토리보드만 만들며, 영상이나 음성 생성 완료로 표시하지 않습니다.

지원 시각화는 function_graph / process_diagram / timeline / comparison / state_transition / text_explanation입니다. 함수는 최대3차 계수·좌표만 받고 임의 수식 코드는 실행하지 않습니다. 그림은 제한된 노드·연결·좌표·동작 데이터만 받습니다. [DSL과 미래 렌더러 계약](docs/STORYBOARD_DSL.md)에 각 파라미터·상한·시간 해석을 정리했습니다.

장면은 총30–60초, 9:16(1080×1920,30fps)이며 3–8개 장면을0초부터 연속 배치합니다. 겹침·공백·길이 초과·잘못된 참조·위조 인용·코드 필드는 검증 오류입니다. 한국어 내레이션은 텍스트만 작성하며 실제 발화 길이는 측정하지 않습니다. 근거가 모자라면 text_explanation과 부족한 맥락을 반환할 수 있습니다.

먼저 실제 할당량을 사용하지 않는 mock 서버로 확인하세요.

```bash
AHA_AI_PROVIDER=mock python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766
```

```bash
curl -X POST http://127.0.0.1:8766/api/storyboard \
  -F 'concept=물의 순환' \
  -F 'question=증발과 응결이 어떻게 연결되나요?' \
  -F 'format=shorts' \
  -F 'target_duration_seconds=45' \
  -F 'student_level=high_school'
```

| multipart 필드 | 규칙 |
| --- | --- |
| concept / question | 기존과 동일한200/2,000자. 하나 이상 필요 |
| file | 기존 PDF/이미지1개·5 MiB 제한. 이미지·스캔 OCR 미지원 |
| format | 생략 또는 storyboard/shorts. 항상 스토리보드 JSON 반환. HTML은 /api/learn |
| target_duration_seconds | 기본45, 정수30–60 |
| student_level | 기본 high_school. foundation/high_school/advanced |
| consent | Gemini에서는 true 필수. mock에는 불필요 |

Gemini 서버에서는 전송 안내를 확인한 뒤 `consent=true`를 추가하세요. 입력과 PDF 내용은 참고 데이터로 전달하며 자료 안의 실행 지시를 따르지 않도록 요청합니다. 응답의 `storyboard`에 명세, `generation`에 Provider·모델·독립 프롬프트 버전·캐시·사용량, `grounding`에 자료 상태를 담습니다. `rendering.status=not_implemented`, `video_generated=false`, `tts_generated=false`입니다.

캐시는 기존 TTL/LRU·중복 요청 공유를 재사용하되 HTML과 별도의 저장소·namespace·프롬프트·스키마를 씁니다. 모델·목표 길이·수준·자료·출력 예산이 다르면 재사용하지 않습니다. 원문을 키·로그로 남기지 않고, 실패한 명세를 캐시하지 않습니다.

```bash
# .env가 Gemini여도 이 명령은 기본 mock입니다. 실제 API 미호출.
python scripts/check_storyboard.py --all
python scripts/check_storyboard.py --concept science --duration 30 --json

# 아래만 실제 Gemini를 호출합니다. 실제 할당량 사용, 자동 재시도 없음.
python scripts/check_storyboard.py --live --concept science
# --live --all은 최대4회 호출하므로 필요한 경우에만 실행하세요.
```

이번 Phase 3-A에서는 실제 Gemini를 호출하지 않았습니다. HTTP 대역과 mock으로 검증했으며 새 스토리보드 스키마에 대한 실제 모델 응답 품질은 미확인입니다. 앞의 실제 생성2건은 Phase 2의 기록입니다. [Phase 3-A 개발·검증 기록](docs/PHASE3A_NOTES.md)을 참조하세요.

## 로컬 실행

Python **3.11 이상**. 이번 검증 환경은 macOS / Python 3.13 / Chrome입니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
# .env가 없는 최초 설정 때만 실행:
cp .env.example .env
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

이미 키가 있는 `.env`는 복사 명령으로 덮어쓰지 마세요. 현재 로컬 설정에는 사용자 키를 보존하고 Gemini Provider와 3.5 모델을 지정했습니다.

**http://127.0.0.1:8765** 에 접속합니다. 파일을 직접 열지 말고 서버 주소를 사용하세요.

1. **내 자료로 시작하기**를 누릅니다.
2. 선택적으로 5 MiB 이하의 텍스트 PDF를 올립니다.
3. 미분계수 개념과 질문을 입력하고 인터랙티브 학습을 선택합니다.
4. Gemini 모드에서는 전송 안내를 확인합니다.
5. 설명·그래프·예제·확인 문제를 학습합니다. 같은 입력을 다시 제출하면 캐시를 재사용합니다.
6. 실패하면 오류를 확인하고 **기본 수학 예제 바로 열기**로 전환합니다.

Gemini가 실패해도 기존 수학·사회 데모·기존 영상은 이용할 수 있습니다. 서버 프로세스 자체가 중단되면 정적 뷰어도 열리지 않습니다.

## 환경 변수와 키

```dotenv
AHA_AI_PROVIDER=gemini
GEMINI_API_KEY=발급받은_실제_키
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_MAX_OUTPUT_TOKENS=4096
AI_TIMEOUT_SECONDS=45
AHA_CACHE_TTL_SECONDS=300
AHA_CACHE_MAX_ENTRIES=64
```

| 항목 | 의미 |
| --- | --- |
| `AHA_AI_PROVIDER` | mock / gemini / elice. `.env.example`은 안전한 로컬 체험을 위해 mock |
| `GEMINI_API_KEY` | Google AI Studio의 Gemini Developer API 키. 서버에서만 사용 |
| `GEMINI_MODEL` | 공식 모델 ID. 기본 3.5 Flash-Lite. 자동 모델 전환 없음 |
| `GEMINI_MAX_OUTPUT_TOKENS` | 출력 한도, 기본 4096 / 500–8192 |
| `STORYBOARD_MAX_OUTPUT_TOKENS` | 스토리보드 전용 출력 예산, 기본8192 / 1024–16384. 기존 HTML 예산은 유지 |
| `AI_TIMEOUT_SECONDS` | 모델 전체 제한 시간, 기본 45 / 1–90초 |
| `AHA_CACHE_TTL_SECONDS` | 결과 재사용 유효 시간, 기본 300 / 0–3600초. 0은 캐시 비활성화·기존 항목 제거 |
| `AHA_CACHE_MAX_ENTRIES` | 프로세스별 최대 캐시 항목, 기본 64 / 1–128 |

환경 변수는 같은 이름의 `.env` 값을 덮어씁니다. 기존 `AHA_AI_MODE`는 호환 별칭이며 새 설정과 충돌하면 오류를 냅니다. 두 항목 중 하나만 사용하는 것을 권장합니다. 서버는 요청마다 설정을 읽으므로 `.env` 설정 변경 후 화면을 새로고침하세요. 코드 변경은 서버를 재시작해야 합니다.

키는 `x-goog-api-key` 헤더에 넣고 URL 쿼리·프론트엔드·응답·일반 로그에 넣지 않습니다. `.env`는 Git에서 제외하며 정적 파일로 제공하지 않습니다. 현재 로컬 파일 권한은 600입니다.

```bash
git check-ignore .env
# 아래 명령의 출력에는 .env가 없어야 합니다.
git ls-files .env
```

프론트엔드 변수나 GitHub에 키를 복사하지 마세요. 키가 노출됐다면 AI Studio에서 폐기·재발급해야 합니다. 이 프로젝트는 Elice 키를 소비하거나 호출하지 않습니다.

## 공식 Gemini 호출 방식

[공식 generateContent 문서](https://ai.google.dev/api/generate-content)에 따라 다음 REST 규격을 사용합니다.

- `POST https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent`
- 인증: `x-goog-api-key`
- 입력: `systemInstruction`, `contents[].parts[].text`
- 출력 설정: `generationConfig.responseMimeType=application/json`, `responseJsonSchema`, `maxOutputTokens`
- 응답: `candidates[].content.parts[].text`, `finishReason`, `usageMetadata`

불필요한 SDK를 추가하지 않고 기존 httpx를 재사용합니다. 모델 ID는 경로·쿼리를 삽입할 수 없도록 검증하고 API 호스트는 고정합니다. 도구·코드 실행·검색·파일 업로드 API는 연결하지 않습니다.

Gemini에는 문서화된 JSON Schema 부분집합만 전달하고 길이·h 간격·수학·인용 조건은 서버 Pydantic 검증으로 다시 확인합니다. 스키마 지원 자체가 설명의 의미적 정확성을 보장하지 않습니다.

공식 자료: [모델](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [JSON 출력](https://ai.google.dev/gemini-api/docs/structured-output), [가격표](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite), [요청 한도](https://ai.google.dev/gemini-api/docs/rate-limits), [모델 목록 API](https://ai.google.dev/api/models).

## 무료 티어 사용 시 주의사항

- 공식 가격표에서 3.5 Flash-Lite의 무료 입력·출력을 확인했습니다. **실제 사용 가능 모델과 RPM/TPM/RPD는 프로젝트·지역·현재 정책에 따라 달라집니다.** 고정된 무료 호출 횟수를 약속하지 않습니다.
- API 키만으로 앱이 결제 연결 상태를 판별할 수 없습니다. 무료 프로젝트인지 AI Studio에서 확인하세요. 유료 프로젝트 키는 같은 호출도 과금될 수 있습니다. 앱은 유료 Elice·다른 모델·유료 Google context cache로 자동 전환하지 않습니다.
- 429는 할당량/요청·토큰 제한, 503은 서비스 부하일 수 있습니다. 자동 재시도로 사용량을 늘리지 않습니다. 재시도 대기 헤더가 있으면 표시합니다.
- **Gemini API 약관에는 18세 미만 대상·접근 가능 앱 제한이 있습니다.** 현재 Gemini 경로는 성인 개발자·평가자의 로컬 PoC 검증용으로 안내합니다. 고등학생 공개 서비스에 적합하다는 검토를 마친 것이 아니며, 체크박스가 이를 해결하는 연령 인증은 아닙니다.
- 무료 서비스의 입력·출력은 Google 제품 개선과 검토에 사용될 수 있으므로 **개인정보·민감정보·기밀 자료를 보내지 마세요.** 성인 평가용 합성 질문·비식별 자료를 사용하세요. API와 소비자 Gemini 구독의 무료 혜택은 구분해야 합니다.

관련 조건은 [Gemini API 이용약관](https://ai.google.dev/gemini-api/docs/terms)을 확인하세요.

## PDF 분석과 결과 캐시

자료는 1개 / 최대 **5 MiB**, 전체 multipart 요청은 6 MiB입니다. PDF·PNG·JPEG·WebP의 확장자·MIME·시작 서명을 검사합니다.

텍스트 PDF는 최대 **20쪽·12,000자**를 별도 프로세스에서 읽습니다. 20쪽 초과, 암호화·손상·복잡도·8초 제한 초과는 오류로 안내합니다. 12,000자 이후가 잘리면 이를 표시합니다. 이미지·텍스트 없는 스캔/빈 PDF의 OCR은 미지원이며 읽지 못한 쪽을 안내합니다. 수식·표·읽기 순서는 불완전할 수 있습니다. 이미지 원본은 Gemini에 보내지 않습니다.

원본 파일·추출 텍스트를 영구 보관하지 않습니다. 업로드 프레임워크의 요청 중 임시 파일은 닫습니다. PDF 프로세스에는 API 키 환경 변수를 넘기지 않고, 지원 OS의 CPU 제한·Linux 주소 공간 제한을 사용합니다. 동일한 메모리 격리를 모든 OS에서 보장하지는 않습니다.

**캐시 정책:**

- Google의 유료 context cache가 아니라 서버 프로세스 내부의 TTL/LRU 결과 캐시입니다.
- 키에는 Provider·모델·프롬프트 버전·실제 프롬프트·스키마·출력 제한·인증 범위가 반영됩니다.
- 키는 프로세스별 임의 비밀값으로 만든 HMAC-SHA256이며 질문·PDF 원문·파일명·API 키를 캐시 키나 로그에 남기지 않습니다.
- 검증한 **출력 명세만** 보관합니다. 설명·인용에 자료의 일부가 포함될 수 있습니다. 해시 키가 출력 내용까지 익명화하거나 암호화하는 것은 아닙니다.
- 동일한 동시 입력은 한 번의 생성 요청을 공유합니다. 오류·불완전 응답·수학·인용 검증 실패는 캐시하지 않습니다.
- 캐시 hit는 API를 재호출하지 않고 `usage={}`, `generation.cached=true`로 표시합니다. 기존 호출의 토큰 사용량을 새 사용량처럼 표시하지 않습니다.
- 응답의 파일명·요청 ID 등은 매번 현재 요청에서 만들므로 다른 파일명이 섞이지 않습니다.
- TTL은 재사용 기한이며 만료 항목의 물리 제거는 다음 캐시 접근 때 이뤄집니다. 서버 재시작 시 모두 사라지고 TTL=0 요청은 캐시를 비웁니다. 디스크·DB에 쓰지 않습니다.
- 캐시는 프로세스별입니다. 여러 worker 간 공유·사용자별 인증 격리는 구현하지 않았으므로 현재 로컬 PoC 범위에서 사용합니다.

## JSON·수학·실행 검증

학습 명세는 개념 설명, 질문에서 추정한 수준·선행 개념, 단계, 시각화 유형·변수, 예제, 확인 문제, 자료 인용·가정을 포함합니다.

허용 시각화는 `secant_tangent_x2` 하나입니다. 함수·기준점·범위는 고정하고 모델은 h 초기값을 선택합니다. h는 −1.2부터 1.2까지 0.0001 간격이며, 예제·문제의 값도 같은 간격으로 제한합니다.

h≠0의 할선 기울기 2+h, 접선 기울기 2, h=0 미정의를 코드로 검증합니다. 확인 문제 문장과 채점도 수치로 구성합니다. 인용은 제공된 페이지의 추출 문자열과 비교합니다. 자연어 설명 전체의 정확성이나 인용의 의미적 관련성을 완전히 검증하지는 않습니다.

임의 실행 코드·다른 함수·추가 JSON 필드는 거절합니다. 고정 스크립트 해시 CSP와 `sandbox="allow-scripts"` iframe을 사용하고 `allow-same-origin`은 주지 않습니다. 검증된 JSON만 전달해 `textContent`로 표시하며 메인 DOM에 AI HTML을 넣지 않습니다. iframe/CSP만으로 완전한 보안을 보장하지 않습니다.

## 오류와 API

| 원인 | 코드 예시 / 동작 |
| --- | --- |
| 키·권한·지역 | `gemini_auth`, 설정 확인 |
| 모델 접근 불가 / HTTP 404 | `gemini_model_unavailable`, 자동 모델 전환 없음 |
| 무료 티어 사전 조건 / HTTP 400 | `gemini_free_tier_unavailable` |
| 한도 / HTTP 429 | `gemini_quota_exceeded`, 대기 시간 안내·기본 예제 |
| 서비스 부하 / HTTP 503 | `gemini_overloaded` 또는 `gemini_unavailable`, 기본 예제·나중에 재시도 |
| 시간 초과 | `gemini_timeout` |
| 출력 잘림·차단·형식 | `gemini_output_truncated`, `gemini_blocked`, `gemini_invalid_response` |
| 수학·인용·스키마 | `invalid_lesson_spec` |
| Elice 선택 | `elice_not_implemented`, 네트워크 호출 없음 |

`GET /api/health`는 모드·설정 형식 확인·캐시 여부·제한 시간을 반환합니다. `ai_configured=true`는 실제 인증·생성 성공을 뜻하지 않습니다.

`POST /api/learn`은 multipart이며 `concept`(200자), `question`(2,000자), `format=html|shorts`, 선택적 `file`, Gemini의 `consent=true`를 받습니다. 개념·질문 중 하나가 필수입니다. 전송 확인은 캐시 조회 전에도 요구합니다.

```bash
curl http://127.0.0.1:8765/api/health
curl -X POST http://127.0.0.1:8765/api/learn \
  -F 'question=h=0을 대입하면 왜 안 되나요?' \
  -F 'format=html' -F 'consent=true'
```

응답은 `mode`, 입력, 자료 처리 상태, `generation`(Provider·모델·요청 ID·캐시·토큰), `verification`, `lesson.spec` 또는 기존 영상입니다. 앱 로그에는 요청 ID·모드·상태·오류 코드만 기록합니다. 일반 오류 응답에는 Google이 반사할 수 있는 원문을 포함하지 않습니다.

## 테스트와 실제 검증

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_api.py tests/test_phase2.py tests/test_providers_cache.py -q
python -m pytest tests/test_storyboard.py -q
# 기존+신규 전체 검사:
python -m pytest -q
node --check frontend/static/workflow.js
```

일반 테스트는 mock·HTTP 대역을 사용하며 실제 API를 호출하지 않습니다. 기존 데모·키 비노출·PDF·Gemini 요청·실패·스키마·수학·인용·캐시 TTL/LRU/동시 중복·모델·프롬프트 변경을 확인합니다.

Phase 3-A 추가 후 전체 **155개**가 통과했습니다. 신규 검사는4개 개념,6종 시각화,30/45/60초, 시간·좌표·참조·인용·코드 거절과 기존 API 응답 유지를 포함합니다.

브라우저 검증은 mock 서버를 실행해 진행합니다.

```bash
AHA_AI_PROVIDER=mock python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766
AHA_BASE_URL=http://127.0.0.1:8766 python tests/browser_smoke.py
AHA_BASE_URL=http://127.0.0.1:8766 python tests/browser_phase2.py
```

설치된 macOS Chrome을 사용합니다. 다른 환경은 `python -m playwright install chromium` 또는 `AHA_BROWSER_EXECUTABLE=/path/to/chrome`을 설정하세요.

명시적인 실제 호출 검증은 **성인 개발·평가용 합성 질문만** 보냅니다.

```bash
python scripts/check_gemini.py
# 실제 요청 2개로 질문별 설명 변화까지 확인:
python scripts/check_gemini.py --compare
```

이 스크립트는 캐시를 우회하며 무료 할당량을 사용합니다. 성공 시 `tmp/gemini-live-check.json`에 시각·모델·요청 ID·사용량·설명 해시를 기록합니다. 키나 본문은 저장하지 않습니다. 실패 시 HTTP 상태와 키를 가린 Google 오류 메시지를 출력합니다. **실제 사용자 입력을 받는 앱 로그에는 이 진단 원문을 출력하지 않습니다.**

실제 FastAPI·PDF·브라우저 그래프와 캐시까지 한 번에 확인하려면 Gemini 서버를 실행한 상태에서 `python tests/browser_live_gemini.py`를 실행합니다. 이 검증은 합성 자료로 새 요청 1건(이미 캐시에 있으면 0건)을 생성하고 같은 입력의 캐시 hit를 확인합니다. 자동 재시도하지 않으며 실제 할당량을 사용합니다. 일반 테스트에는 포함되지 않습니다.

## 소스 구조

```text
backend/app/
  config.py                 서버 환경 설정
  providers/
    base.py, __init__.py     공통 계약·Provider 선택
    mock.py                 고정 예제
    gemini.py               Google generateContent
    elice.py                네트워크 없는 준비 구현체
  schemas.py                학습 명세·수학·인용 검증
  storyboard_schema.py     별도 범용 영상 DSL·시간·참조 검증
  services/
    lessons.py              PDF → Provider → 검증 → 캐시 → 응답
    prompts.py              버전이 있는 프롬프트
    validation.py           공통 JSON 검증
    cache.py                메모리 TTL/LRU·동시 요청 공유
    materials.py, pdf_worker.py
    storyboard*.py          스토리보드 생성·mock·독립 프롬프트·검증
    uploads.py              기존·신규 API의 공통 파일 검증
  routes/storyboard.py      POST /api/storyboard
frontend/                   기존 랜딩·폼·격리된 그래프
scripts/prepare_frontend.py  원본 + 폼으로 실행 HTML 재구성
scripts/check_gemini.py      명시적 실제 호출 검증
scripts/check_storyboard.py  기본 mock / 명시적 --live 스토리보드 검증
tests/                      회귀·Provider·캐시·브라우저 검증
references/                 보존한 HTML·기획 PDF
```

`frontend/workflow.html`을 수정하면 `python3 scripts/prepare_frontend.py`로 index를 재구성합니다. index 직접 수정은 재구성 시 덮어씁니다. 원본 Google Fonts 링크는 유지하며 연결이 없으면 시스템 글꼴을 사용합니다. 로컬 변경은 아직 GitHub에 커밋·푸시하지 않았습니다.
