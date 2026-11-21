# Phase 3-C · 웹 숏츠 생성·재생·다운로드

## 시작 상태

2026-11-21, `main`, `8d616a1`에서 시작했습니다. 작업 트리는 깨끗했고 Phase 3-A의 StoryboardSpec/DSL/API와 Phase 3-B의 실제 MP4 렌더러가 존재했습니다. 기존 렌더러는 동기 함수가 별도 worker를 실행하고 전역 단일 실행 잠금과 시간·디스크 제한을 적용했지만 외부 취소 신호나 웹 작업 관리 기능은 없었습니다.

Phase 3-A의 `create_storyboard()`와 Phase 3-B의 `render_storyboard()`를 재사용했습니다. 기존 HTML 학습·Provider·PDF 분석·명세 캐시·원본 HTML·시안 영상은 유지하며 기존 API 응답을 바꾸지 않았습니다. 실제 Gemini 호출은 이번 단계에서 수행하지 않았습니다.

## 구조와 수정 파일

- `services/video_jobs.py`: 서버 수명에 묶인 비동기 대기열·직렬 실행기, 메모리 상태, 시간/용량/수명 제한, 취소·만료·파일 lease.
- `routes/videos.py`: 생성202, 조회, 취소/삭제, 세션 소유권·동일 출처 확인, 보호된 MP4 Range 응답.
- `video_config.py`: AI 키 설정과 분리한 작업 정책. `.env.example`에 기본값과 범위가 있습니다.
- `main.py`: lifespan에서 실행기 시작·정상 종료, 라우터 추가, 영상 오류 응답의 no-store.
- `services/storyboard_input.py`, `routes/storyboard.py`: 기존 multipart 규칙을 공통 함수로 옮겨 신규 API에서 재사용.
- `services/storyboard.py`: 자료 분석/구성 시작 콜백만 추가. 기존 반환 JSON은 유지.
- `rendering/engine.py`: Event 취소·실제 단계 콜백, 부모 등록 gate, 자식 추적, 작업 안의 브라우저 임시 디렉터리.
- `rendering/processes.py`: psutil의 PID/생성 시각 기반 자식 추적·종료와 부모 종료 watchdog. `backend/requirements.txt`에 설치 환경의 psutil7.2.2를 명시했습니다.
- `rendering/worker.py`: 실제 TTS/캡처/인코딩/검사 단계·캡처 프레임 수 기록, 부모 사망 감시 시작.
- `frontend/workflow.html`, `workflow.js/css`, `video-jobs.js`, `scripts/prepare_frontend.py`: 기존 폼에 숏츠 설정, 진행 카드, 재시도/취소/예시, 세로 플레이어/다운로드, 복구를 추가. 생성된 index만 재구성하며 원본 참조 HTML은 보존.
- `tests/test_video_jobs.py`, `tests/test_rendering.py`, `tests/browser_phase3c.py`: 정책·경쟁 상태·프로세스·실제 웹 영상 검증. 기존 브라우저 smoke는 샘플을 명시적으로 여는 버튼을 사용하도록 갱신했습니다.

## 파이프라인과 상태

```text
POST multipart 유효성/동의/파일 형식 검사 → 202 + job_id
  → queued
  → generating / analyzing   : 기존 PDF 분석
  → generating / storyboard  : 기존 Provider/프롬프트/검증/캐시
  → rendering / waiting_renderer : 기존 CLI 잠금이 잡혀 있으면 대기
  → rendering / tts, browser, frames, encode, verify : 실제 worker 진행
  → 렌더러의 MP4 ffprobe + 전체 디코딩 + 프로세스 정리
  → completed / ready : 보호된 URL 공개
```

실패는 `error.phase=generation|rendering`과 code/message/scene_id로 구분합니다. API 요청은 렌더링 완료를 기다리지 않습니다. 생성은 별도 asyncio 실행기에서, 동기 렌더러는 전용 ThreadPoolExecutor(max_workers=1)에서 실행하므로 FastAPI 이벤트 루프를 막지 않습니다. 영상 생성은 기존 HTML 페이지의 녹화가 아닙니다.

UI는 단계와 실제 프레임 수만 표시합니다. 프레임 비율을 전체 퍼센트로 표시하거나 예상 완료 시간을 만들어내지 않습니다. mock에서는 예제 스토리보드임을 밝히고 실제 로컬 렌더링과 AI 생성을 구분합니다. 실패 시 원인·재시도·기존 샘플 보기를 제공합니다.

## 소유권·저장·복구

- POST에서256bit 무작위 HttpOnly/SameSite Strict 쿠키를 발급합니다. HTTPS에서는 Secure, cookie path는 `/api/videos`, 수명24시간입니다.
- 서버에는 소유자 해시만 저장하고 상태·파일·DELETE 모두 확인합니다. ID만 아는 타인/쿠키 없는 요청은404입니다. 토큰은 URL/JSON/localStorage/로그에 넣지 않습니다.
- 변경 요청은 다른 Origin와 cross-site를 거절합니다. 인터넷 공개용 계정 인증·CSRF 전체 위협 모델을 완성했다는 의미는 아니며 로컬 PoC로 운영합니다.
- `tmp/video-jobs`는0700이며 static mount가 없습니다. 파일 경로는 서버의 검증된 job ID로만 결정합니다. 사용자 입력으로 임의 경로·URL을 받지 않습니다.
- `/file`은 completed와 소유권을 확인하고 FileResponse로 스트리밍합니다. Range206/416, inline 재생과 `?download=1` attachment를 지원합니다. Cache-Control은 private,no-store입니다.
- 파일 lease는 이미 승인된 스트림의 경로를 유지합니다. 완료 작업 DELETE/만료는 새 접근을 막고 마지막 스트림 후 물리 삭제합니다. 이미 전송한 바이트는 회수할 수 없습니다.
- localStorage에는 마지막 job_id만 저장합니다. 입력 질문·PDF·토큰은 저장하지 않습니다. 같은 origin과 쿠키에서 새로고침/브라우저 재실행 시 상태를 다시 조회합니다. 브라우저 종료만으로 작업을 취소하지 않습니다.
- 메모리 상태이므로 서버 재시작은 복구하지 않습니다. 정상 shutdown은 실행 작업 종료를 기다리고 웹 작업 폴더를 삭제합니다. 갑작스러운 부모 사망은 watchdog이 worker/자식을 종료하며 다음 시작에서 이전 작업 폴더를 제거합니다. 이전 job ID는404입니다. CLI의 `tmp/videos`는 보존합니다.

## 제한과 취소의 확정 시점

기본 대기3개, 전체 기록16개, 세션당 활성2개, 수명3600초(생성 시점부터), 처리900초(실행 시작부터), 웹 저장소2048MiB입니다. 기존 렌더러의 작업별512MiB/600초와 OS 파일 제한·여유 공간 검사·단일 잠금도 유지합니다. 큐/기록 한도429, 공간 부족507입니다. 실패·취소 tombstone은 기록 한도가 필요할 때 먼저 제거될 수 있습니다.

전용 저장소는 서버 프로세스 잠금으로1개 API 프로세스만 관리합니다. `uvicorn --workers 1`로 실행하세요. 외부 CLI가 렌더 잠금을 사용 중이면 스토리보드를 다시 생성하지 않고 제한 시간 안에서 대기합니다. 브라우저 프로필도 렌더링 작업의 TMPDIR 안에 있어 강제 취소 때 용량 제한과 정리에 포함됩니다.

DELETE는 먼저 cancel_requested를 설정합니다. 대기 중이면 실행할 프로세스가 없어 바로 cancelled, 구성 중이면 비동기 생성 task를 취소하고 기존 PDF/Provider 정리를 기다립니다. 렌더링 중이면 Event를 기존 엔진에 전달합니다. 엔진은 부모·자식을 추적하고 분리된 Chrome 세션까지 종료·확인한 뒤 임시 파일을 정리합니다. 실행 중 DELETE의 응답202는 취소 접수이며 cancelled 확정이 아닙니다. 종료 확인 실패는 failed/cleanup_failed이며 cancelled로 숨기지 않습니다.

완료·취소·실패의 공개 상태는 서버 루프에서 직렬 반영합니다. 취소 요청 후 렌더러가 늦게 성공해도 결과를 삭제하고 URL을 공개하지 않습니다. 완료가 먼저 확정된 뒤 DELETE되면 완료 영상 삭제로 처리합니다. 취소/실패 확정은 실행기의 정리 이후입니다. 부모가 갑자기 죽는 경우를 위해 worker는 부모 등록 파일을 기다린 뒤 시작하며 watchdog이 부모 PID 변경을 감지합니다. 이 방식은 OS 전체 격리나 전원 장애 시의 즉시 파일 정리를 보장하지 않습니다.

## 실제 검증 결과

일반 pytest **206개 통과**(기존183개 + 신규23개). 실제 Gemini/Chrome/TTS/MP4를 일반 pytest에서 실행하지 않습니다. 무해한 실제 대역 프로세스를 사용한 detached 자식 종료와 부모 사망 watchdog 검사는 포함합니다. 관리형 sandbox의 macOS 프로세스 조회 제한 때문에 전체 프로세스 검증은 승인된 로컬 실행 권한으로 수행했습니다. 제한된 환경에서 조회가 불가능하면 프로덕션 코드도 렌더링을 시작하지 않고 process_tracking_denied를 반환합니다.

검사 범위:

- 202 접수, 상태/파일/삭제의 소유권, HttpOnly/Strict 쿠키, Range206/416와 다운로드.
- multipart·동의·동일 출처, 위조 ID/임의 경로 거절.
- 대기열/세션/기록/공간 한도, 취소 기록 정리, 외부 CLI 잠금 대기 시 재생성 없음.
- 구성 실패와 렌더링 실패 구분, 구성 중 취소.
- 렌더 완료/실패와 취소 경합, 정리 확인 전 rendering 유지, cleanup_failed가 cancelled가 되지 않음.
- 처리 제한·TTL·스트림 lease·만료 파일 정리, 재시작과 단일 서버 잠금.
- 실제 detached 자식 종료와 갑작스러운 부모 사망 시 watchdog 정리.

실제 웹 검증 명령:

```bash
AHA_AI_PROVIDER=mock AHA_VIDEO_PREVIEW=true AHA_VIDEO_FPS=3 \
  python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766 --workers 1
python tests/browser_phase3c.py
```

검증 환경은 macOS/Python3.13/Playwright1.65.2/설치된 Chrome/Yuna/FFmpeg9.0.2입니다. 실제 PDF를 업로드하고 물의 순환30초를 생성했습니다. 브라우저 새로고침 후 작업을 복구하고 모바일390×844에서 세로 플레이어·재생·다운로드를 확인했습니다. MP4는 **30.000초,540×960,3fps,H.264 + AAC48kHz**, 다운로드608,242bytes였습니다. ffprobe와 기존 렌더러의 전체 디코딩도 통과했습니다.

실제 실행 중인 다음 작업에서 캡처 단계까지 기다린 뒤 취소했고 **worker와 Chrome 등을 포함한9개 프로세스 종료**, 작업 폴더 삭제와 URL 비공개를 확인했습니다. 대기 중 작업도 취소했습니다. 다른 브라우저 세션의 상태/파일 요청은404였고 Range 재생은206이었습니다. 생성 후 기존 HTML 학습도 열렸습니다.

Gemini 사용량 초과 UI는 명시적인 HTTP 대역으로만 검증했습니다. 실패 메시지·재시도·기존 샘플 보기가 표시됐으며 실제 Gemini 호출 성공으로 계산하지 않습니다.

결과물은 Git에서 제외된 `tmp/phase3c-checks/`에 있습니다:

- `web-generated.mp4`: 실제 웹에서 다운로드한 결과.
- `verification.json`: 작업 ID·영상 크기·다운로드 크기·취소 프로세스 수·검증 항목. 질문·자료·키 없음.
- `generating-mobile.png`, `completed-mobile.png`, `failure-fallback-mobile.png`: 실제 화면.

기존 `browser_smoke.py`, `browser_phase2.py`, `browser_rendering.py`도 통과했습니다. 원본 수학/사회 데모, 업로드·PDF·수학 슬라이더·모바일·샘플 재생,6종 영상 DSL의 결정론적 프레임·대체·네트워크 차단이 유지됩니다. 테스트 경고는 기존 FastAPI TestClient/httpx deprecation1개입니다. 참조 HTML 해시도 기존 `63cccf869c0c75aedffc12fbe00cc7fb7c5be30210372c076f97261167f0e2b1`과 같습니다.

## 남은 범위

영속 DB/분산 큐/계정 인증·다중 worker·클라우드 저장·공개 배포는 구현하지 않았습니다. 서버 재시작을 넘는 작업 복구는 지원하지 않습니다. 로컬 한국어 TTS는 macOS이며 Linux/Windows 엔진은 후속 작업입니다. 생성 설명의 전체 사실성·음성의 주관적 품질·미성년자 대상 공개 서비스 적합성을 검증했다고 주장하지 않습니다. 실제 Gemini 검증은 기존 명시적 스크립트에서만 수행하며 이번 단계는 추가 할당량을 사용하지 않았습니다.

참고: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [Starlette FileResponse 구현](https://github.com/Kludex/starlette/blob/main/starlette/responses.py), [psutil 프로세스 문서](https://psutil.io/).
