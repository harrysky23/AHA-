# Phase 2 · Provider / Gemini / 캐시 구현·검증

2026-11-21 / macOS, Python 3.13, Chrome.

**실제 `gemini-3.5-flash-lite` 생성과 FastAPI·PDF·그래프·캐시 경로를 검증했습니다.** mock/HTTP 대역 검증과 실제 검증을 아래에 구분합니다. Elice와 새 숏츠(Phase 3)는 연결하지 않았습니다.

## GitHub와 기존 코드 확인

- GitHub: `harrysky23/AHA-`, `main`의 `2fc06a248f253c2b002b38730592a711783217bb`. 확인 당시 로컬 HEAD와 같았습니다.
- 원격의 Phase 1은 정적 랜딩·데모·파일 검증·고정 응답으로 구성되어 있었습니다.
- 앞선 로컬 Phase 2 변경을 재사용했습니다. 새 프론트엔드 프레임워크를 도입하지 않았습니다.
- 원본 HTML SHA-256 `63cccf869c0c75aedffc12fbe00cc7fb7c5be30210372c076f97261167f0e2b1`을 회귀 테스트로 확인합니다. 원본 영상도 유지했습니다.
- 현재 변경은 작업 폴더에 있으며 커밋·푸시하지 않았습니다. 키가 있는 `.env`는 Git에서 제외합니다.

## 수정 구조

`providers/base.py`의 공통 계약은 질문·개념·PDF 문맥을 받아 `ProviderResult(spec, model, usage)`를 반환합니다.

- `MockProvider`: 기존 f(x)=x², a=1 고정 예제. 질문 분석을 흉내 내지 않습니다.
- `GeminiProvider`: 공식 REST generateContent, JSON 스키마와 서버 검증.
- `EliceProvider`: 네트워크 코드 없는 준비 구현체. 실제 선택 시 명확한 미연결 오류를 반환합니다.
- `services/lessons.py`: 자료 추출 → Provider 선택 → 공통 검증 → 결과 캐시 → 응답.
- `services/validation.py`: JSON 중복 키·비정상 수치·추가 필드·수학·인용 검증.
- `services/cache.py`: 메모리 TTL/LRU 및 동일 동시 요청 공유.
- 기존 폼, 격리된 그래프, PDF 처리기, 원본 보존 스크립트를 재사용했습니다.
- 이전 Elice HTTP 어댑터와 실제 호출 스크립트는 제거했습니다. Elice의 실제 사양 확정 전 호출하지 말라는 수정 요청을 반영했습니다.

## 공식 규격과 모델 선택

공식 [generateContent 규격](https://ai.google.dev/api/generate-content)에 따라 고정 Google 호스트의 `/v1beta/models/{model}:generateContent`를 사용합니다. 키는 헤더에만 넣습니다. 질문·추출 텍스트는 contents에, 지시와 JSON 스키마는 systemInstruction/generationConfig에 전달합니다. 도구·임의 코드 실행은 연결하지 않습니다.

초기 사용자 지정 모델 `gemini-2.5-flash-lite`는 ListModels에는 나왔지만 실제 생성과 최소 JSON 요청에서 **404 NOT_FOUND**를 반환했습니다. 원인을 계정 문제 하나로 단정하지 않았습니다. 사용자에게 알린 뒤 명시적인 요청에 따라 `gemini-3.5-flash-lite`로 변경했습니다.

3.5 첫 실제 호출은 **503**, 다음 메시지를 반환했습니다.

> This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.

이 실패는 무료 한도 초과인 429와 구분합니다. 앱에 자동 재시도를 추가하지 않았으며, 문서 정리 후 수동 검증에서 생성이 성공했습니다.

[공식 가격표](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite)는 해당 모델의 무료 입력·출력을 안내합니다. 사용자는 무료 등급 키를 준비했다고 알려 주었으며 그 키의 실제 호출이 성공했습니다. API 응답만으로 결제 계정·프로젝트 티어를 확정했다고 주장하지는 않습니다. 한도는 [공식 요청 제한 문서](https://ai.google.dev/gemini-api/docs/rate-limits)와 AI Studio에서 확인해야 합니다.

무료 티어의 데이터 이용·18세 미만 대상 앱 제한은 [공식 이용약관](https://ai.google.dev/gemini-api/docs/terms)에 명시되어 있습니다. 현재 Gemini 경로는 성인 개발자·평가자의 비식별 로컬 PoC 검증용으로 안내하고, 고등학생 공개 서비스 적합성 검토나 연령 인증을 구현했다고 주장하지 않습니다.

## 자료·검증·실행 경계

- 파일 5 MiB / PDF 20쪽 / 총 12,000자 / 별도 프로세스 8초. 수식·표·읽기 순서는 불완전할 수 있습니다.
- 이미지 OCR·스캔 OCR은 미지원입니다. 읽지 못한 페이지·암호화·손상·크기·시간 초과를 안내합니다.
- 입력과 자료는 프롬프트에서 신뢰하지 않는 데이터로 분리합니다. 프롬프트만으로 모든 주입을 막는다고 주장하지 않습니다.
- JSON에는 설명·추정 수준·핵심 개념·변수·수치 예제·확인 문제·출처·가정을 포함합니다.
- f(x)=x², a=1에서 2+h / 접선 2 / h=0 미정의, h 간격 0.0001, 예제·정답·인용 일치를 확인합니다.
- 실제 Gemini 출력에도 동일한 검증을 적용했습니다. 자연어 의미 전체는 검증하지 않습니다.
- 명세는 고정 스크립트 CSP, same-origin 권한 없는 sandbox iframe에 데이터로 전달하고 textContent로 표시합니다. AI JavaScript는 실행하지 않습니다.

## 캐시

- 모델·Provider·프롬프트 버전·실제 프롬프트·스키마·출력 제한·인증 범위로 키를 구성합니다.
- 프로세스별 임의 비밀값의 HMAC 키를 사용합니다. 원문이나 키를 로그에 쓰지 않습니다.
- 검증된 출력 명세만 저장합니다. 출력의 인용에 원문의 일부가 포함될 수 있어 완전 익명화라고 주장하지 않습니다.
- 기본 TTL 300초, 최대 64개, LRU. 만료는 재사용 제한이며 물리 제거는 이후 접근·서버 종료에 이뤄집니다. TTL=0 요청은 기존 캐시를 비웁니다.
- 동시 중복 입력은 한 번의 생성을 공유합니다. 실패와 검증 오류는 저장하지 않습니다.
- hit는 API 재호출 없이 현재 요청의 파일명·요청 ID로 응답하고 새 사용량은 빈 객체로 반환합니다.
- 디스크 저장·worker 간 공유·운영 사용자 인증 격리는 구현하지 않았습니다.

## 자동 검증

`python -m pytest tests/test_api.py tests/test_phase2.py tests/test_providers_cache.py -q`: **80개 통과**.

포함 범위:

- 원본·정적 파일·영상 Range·파일·입력·전체 요청 한도.
- 텍스트 PDF와 한글 텍스트 레이어 추출, 암호화·손상·텍스트 없음·잘림·페이지·시간 제한.
- Gemini 공식 URL·헤더·입력·JSON 스키마·응답 처리. 실제 토큰을 쓰지 않는 HTTP 대역입니다.
- 400의 무료 티어 조건·잘못된 요청, 401/403, 404, 429·Retry-After, 500/503/504, 네트워크·타임아웃·차단·잘림·응답 크기·형식 오류.
- Elice 구현이 HTTP 클라이언트를 열지 않음.
- 키·본문·응답 비노출, 미동의 거절, 정적 .env 접근 거절.
- TTL·LRU·비활성화·변경된 모델/질문/자료/프롬프트/스키마/인증 범위, 동시 중복 공유·대기자 취소·실패 미저장·반환 객체 변경 격리.
- 캐시 hit의 잘못된 파일명 혼입·사용량 중복 표시 방지.

Python compile, JavaScript syntax, 의존성 검사를 수행했습니다. TestClient의 httpx deprecation 경고 1개는 남아 있으며 테스트 실패는 아닙니다.

`tests/browser_smoke.py`, `tests/browser_phase2.py`: 기존 수학·사회·영상, 업로드·PDF·확인 문제·고정 mock·격리·오류 fallback·390px 모바일 시나리오 통과. Gemini UI의 429 모의 응답은 실제 API 호출로 계산하지 않습니다.

## 실제 호출·화면 검증

1. `python scripts/check_gemini.py`: 합성 질문으로 **실제 Gemini 생성 1회** 성공, JSON·수학 검증 통과.
   - 기록: `tmp/gemini-live-check.json`.
   - 모델·요청 ID·사용량·설명 해시만 저장하며 키·본문은 저장하지 않습니다.
2. `python tests/browser_live_gemini.py`: **새 API 생성 1회**로 합성 PDF·질문 → FastAPI → Gemini JSON → 수학·인용 검증 → 실제 iframe 그래프 확인.
   - h=-0.1의 기울기 1.9, h=0.0001의 2.0001, h=0의 미정의 표시 확인.
   - 동일 입력 재제출은 캐시 hit, 새 사용량 없음, 동일 명세를 반환했습니다.
   - 기록: `tmp/gemini-live-ui.json`, 화면: `tmp/screenshots/gemini-live-graph.png`.
3. 성공한 실제 생성은 총 **2건**입니다. 앞선 404·503 실패를 성공으로 세지 않았습니다. 새로운 질문이나 모델마다 자동으로 요청하는 테스트는 아닙니다.

유료 context cache, Elice, 새 영상 생성은 이 검증에 사용하지 않았습니다.

## 남은 한계

무료 프로젝트 여부·실제 잔여 할당량은 AI Studio에서 확인해야 합니다. 모델 목록 조회 성공이 생성 가능성을 보장하지 않는 사례도 직접 확인했습니다. 서비스 부하·무료 쿼터는 변할 수 있습니다.

Safari·Firefox·실기기·운영 부하·임의 수학 문제·자연어 설명의 완전 검증은 수행하지 않았습니다. 운영 인증·사용자별 저장소·다중 worker 캐시는 후속 범위입니다. 현재 보안·연령 안내가 공개 학생 서비스의 적합성 검토를 대체하지 않습니다.
