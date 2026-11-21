# Phase 3-B · 로컬 영상 렌더링 엔진

## 시작 상태와 범위

- 2026-11-21, `main`, 시작 커밋 `6cbd722 feat: 범용 영상 DSL·스토리보드 생성`. 작업 트리는 깨끗했습니다.
- `storyboard_schema.py`, 6종 DSL, `/api/storyboard`, mock/Gemini Provider, 자료 추출·캐시가 이미 구현되어 있음을 확인했습니다.
- 이번 변경은 검증된 명세에서 독립적인 숏츠 MP4를 만드는 로컬 엔진입니다. HTML 학습 뷰어를 녹화하지 않습니다.
- Gemini·외부 영상·외부 TTS API를 호출하지 않았습니다. 합성 mock 명세를 사용했으며 실제 AI 스토리보드 내용 품질을 새로 검증했다고 주장하지 않습니다.
- 기존 Provider·`LessonSpec`·업로드·PDF 추출·캐시·API 응답·프론트엔드·참조 HTML·기존 영상 파일은 변경하지 않았습니다. 작업 요청/진행률/다운로드 화면은 Phase 3-C입니다.

## 구현 파일과 흐름

```text
StoryboardSpec 재검증
  → 사용자별 동시 실행1개 잠금
  → 제한된 환경의 별도 worker
  → 장면별 MacOSSay(TTSEngine) → ffprobe 발화 길이 → atempo/pad → 연결
  → 소유한 HTML/CSS/SVG + 결정론적 render(t)
  → 네트워크 차단 Playwright → PNG 프레임
  → FFmpeg H.264 + AAC → ffprobe → 전체 디코딩
  → 성공한 MP4와 *.render.json만 출력 경로에 공개
  → 중간 파일 정리
```

- `backend/app/rendering/core.py`: 오류 코드, 옵션, 시간·용량·여유 공간 검사, shell=False 도구 실행.
- `engine.py`: 공개 동기 함수 `render_storyboard`, 재검증, 파일 잠금, worker 생성·감시·종료, 성공 시 덮어쓰기 없는 결과 공개.
- `worker.py`: 렌더링 실행, 파일당 OS 용량 제한, FFmpeg 인코딩·미디어 형식 검사·전체 디코딩.
- `browser.py`: 고정 로컬 템플릿, 해시 기반 CSP, 비영구 브라우저·offline·route 차단·WebSocket 차단·service worker 차단.
- `assets/scene.html/css/js`: 6종 시각화와 고정 영역·모션·문장 분할. 문자열은 모두 textContent로 전달합니다.
- `tts.py`: 교체 가능한 `TTSEngine`과 macOS `say` Yuna 구현. 내레이션을 명령 인자 대신 stdin으로 전달합니다.
- `scripts/render_storyboard.py`: JSON 객체/스토리보드 API 응답 또는 네 가지 mock 입력. `.env` 로드·AI 호출 없음.
- `requirements-render.txt`: 렌더링용 Playwright 의존성을 분리했습니다. 개발 의존성은 이를 포함합니다.

## 렌더링 해석과 레이아웃

| DSL | 구현 |
| --- | --- |
| function_graph | 계수로 최대3차 다항식을240구간으로 계산·clip. 곡선 결합 마커는 x 보간 후 y 재계산. 수직 연결선은 벡터로 처리하고 두 점이 일치하면 숨김 |
| process_diagram | 정규화 노드, 노드 경계 밖 화살표, 간선 이동 점, 라벨·설명 |
| timeline | position에 따라 세로 배치. 겹칠 정도로 가까운 사건은 텍스트 대체 |
| comparison | 두 열·공통 항목·강조, 긴 문장은 축소 또는 대체 |
| state_transition | 선언된 전이와 step으로 현재 상태 선택. 위쪽 상태도와 아래쪽 자료 배열·제외 범위·강조 인덱스 분리 |
| text_explanation | 핵심 문장 페이지, 페이드·이동. 대체 장면은 표시와 기록 포함 |

제목·그림·주석·자막 영역을 분리했습니다. 글자 크기와 줄바꿈을 검사하고, 주석/내레이션은 길이에 따라 나눕니다. 검증된 시각화라도 노드가 겹치거나 텍스트가 너무 밀집하면 고정 텍스트 렌더러로 대체합니다. `layout.fallbacks`는 장면 ID와 고정 원인 코드를 담습니다. 스키마에 없는 타입이나 실행 코드 필드를 받아서 대체하는 방식은 허용하지 않습니다.

AHA!의 보라·노랑·분홍과 밝은 카드·짙은 자막 색을 재사용합니다. 네트워크 없는 macOS에서 설치된 Apple SD Gothic Neo를 사용하며 Jua/Noto Sans KR 파일을 내려받거나 포함하지 않았습니다. 원본 랜딩의 폰트 링크는 유지합니다.

프레임은 실제 시계·랜덤·CSS 애니메이션 없이 명시적 시점으로 계산합니다. fractional CSS zoom에서 모서리 픽셀 편차를 발견해 **1080×1920 고정 캡처와 정수 HTML 좌표**를 사용하고, 동적 내부 카드는 단순한 경계로 그립니다. 프리뷰는 FFmpeg에서540×960으로 축소합니다. 따라서 프리뷰의 주된 비용 절감 수단은 낮은 FPS입니다. 동일 Chrome/OS/폰트 환경의 PNG 일치를 검사하며 환경 간 비트 단위 결과 일치는 보장하지 않습니다.

## 음성·자원·실패 정책

- macOS Yuna,185wpm. 장면별 실제 발화 길이를 ffprobe로 측정합니다.
- 장면 끝150ms를 남기고 짧은 음성은 무음을 채웁니다. 긴 음성은 최대1.35배 atempo 후 채우며 그 이상은 `narration_too_long`과 장면 ID를 반환합니다. 말을 자르거나 명세 시간을 바꾸지 않습니다.
- 자막은 문장 길이와 장면 시간에 비례한 분할 표시입니다. 단어별 정렬·강제 음소 동기화는 구현하지 않았습니다.
- 동시1개(`flock`, 동일 OS 사용자·다른 프로세스/체크아웃에도 적용). 대기열 없이 `render_busy`를 반환합니다.
- 기본600초, 허용10–1800초. 부모가100ms 간격으로 작업 디렉터리와 시간을 감시하고 worker·자식 프로세스 그룹을 종료합니다. 개별 도구에도 남은 시간 timeout을 전달합니다.
- 기본 임시 파일 합계512MiB, 최대 설정2GiB, 여유 공간256MiB 이상. 파일당 RLIMIT_FSIZE도 적용합니다. 감시 주기 사이의 일시적 초과는 가능하며 OS 컨테이너 디스크 할당량을 대신하지 않습니다.
- 실패·시간/용량 초과·Ctrl+C에서 임시 디렉터리를 정리하고 불완전 MP4를 공개하지 않습니다. 부모 강제 SIGKILL/전원 중단까지 자동 정리를 보장하지 않습니다.
- `render_timeout`, `disk_limit`, `disk_full`, `tts_unavailable`, `tts_failed`, `narration_too_long`, `browser_failed`, `frame_failed`, `layout_overflow`, `encode_failed`, `invalid_mp4`, `decode_failed` 등으로 원인을 구분합니다.
- 오류는 code/message/scene_id만 CLI stderr로 내보냅니다. subprocess stderr·원문 질문·내레이션·키를 일반 로그로 출력하지 않습니다. worker/도구에 API 키를 상속하지 않습니다.
- 새 브라우저 프로필·CSP·요청 차단을 사용하지만 OS 전체 보안 격리나 모든 브라우저 취약점 방어를 보장하지 않습니다. 자료의 의미·과학/사회 전체 사실성·교육적 적합성도 별도 검토 대상입니다.

## 실제 검증

환경: macOS / Python3.13 / Playwright1.65.2 / 설치된 Google Chrome / 로컬 Yuna / FFmpeg9.0.2. FFmpeg는 이번 단계에서 Homebrew로 설치했습니다.

```bash
python -m pytest -q
python tests/browser_rendering.py
python scripts/render_storyboard.py --all-mocks --preview --fps 3 --output tmp/videos/phase3b
```

일반 pytest **183개 통과**(기존155개 + 신규28개). 외부 AI·실제 영상 생성을 실행하지 않습니다. 바쁜 잠금, 음성 과다/잘못된 길이, TTS 제어문자 무력화·비macOS 오류, 시간/디스크/여유 공간 제한, 실제 대역 child 종료·정리, worker의 키 비상속, 출력 덮어쓰기 방지, 잘못된 미디어 거절을 포함합니다. 기존 FastAPI TestClient의 의존성 deprecation 경고1개가 있으며 실패는 없습니다.

실제 브라우저 검사:

- 6종 시각화의 레이아웃과 동일 시점 PNG 바이트 일치.
- 별도 브라우저 실행에서 수학 프레임 일치, 다른 시점 후 되돌아와도 일치.
- 중간 시점의 곡선 결합 마커가 y=x²를 유지하고 이진 탐색 상태가 full → right → found로 변화.
- 노드 겹침 시 scene_1만 텍스트로 대체하고 원인 기록.
- 긴 한국어 제목·주석·자막의 영역 넘침 없음, 마크업 문자열은 평문, hide/reveal/highlight 상태 검사.
- 외부 fetch 차단, 직접 탐색 요청도 차단. 결과는 `tmp/rendering-checks/checks.json`과 PNG에 기록.

실제 출력(각 파일은 Git에서 제외):

| 개념 | 파일 | 길이 | 영상 | 음성 | 대체 |
| --- | --- | --- | --- | --- | --- |
| 미분계수 | `tmp/videos/phase3b/math.mp4` | 45.000초 | 540×960,3fps,H.264 | AAC,48kHz,mono,45초 | 없음 |
| 물의 순환 | `tmp/videos/phase3b/science.mp4` | 45.000초 | 동일 | 동일 | 없음 |
| 수요와 공급 | `tmp/videos/phase3b/social.mp4` | 45.000초 | 동일 | 동일 | 없음 |
| 이진 탐색 | `tmp/videos/phase3b/cs.mp4` | 45.000초 | 동일 | 동일 | 없음 |
| 미분계수 기본 설정 | `tmp/videos/phase3b/math-1080.mp4` | 45.000초 | 1080×1920,30fps,H.264 | AAC,48kHz,mono,45초 | 없음 |

다섯 파일 모두 ffprobe의 컨테이너·영상·오디오 길이/코덱 검사를 통과하고 FFmpeg로 전체 영상·오디오를 오류 없이 디코딩했습니다. 프리뷰 네 파일에서2/7/25초 실제 MP4 프레임12개를 추출했고 수학 그래프, 과정도 화살표, 비교 글자 배치, 이진 탐색의 찾음 상태를 직접 검사했습니다. 프레임은 `tmp/videos/phase3b/frames/`에 있습니다. 장면별 음성 측정 결과는 각 `*.render.json`에 있습니다.

`python tests/browser_rendered_videos.py tmp/videos/phase3b`로 다섯 MP4를 실제 Chrome에서 로드하고5초로 탐색한 뒤 재생 시간이 증가함을 확인했습니다. 영상 오류 없이 통과했으며 모든 플레이어에서의 재생이나 음성의 주관적 품질을 검증한 것은 아닙니다.

최종 worker의 음성 단계별 오류 위치 기록을 확인하면서 `cs-30-preview.mp4`도 생성했습니다(30초,540×960,1fps). 2–4번 장면은 약1.006/1.139/1.164배로 발화를 조정했으며 ffprobe와 전체 디코딩이 통과했습니다. 45초 예제에서는 전 장면 속도1.0으로 무음 채움만 사용했습니다. 작업 종료 후 `.aha-render-*` 임시 디렉터리가 남지 않았습니다.

기존 `browser_smoke.py`와 `browser_phase2.py`도 mock 서버8766에서 통과했습니다. 원본 수학/사회 데모, 업로드·PDF·격리 그래프·음수/0 처리, 기존 영상 재생, 모바일, 동의·실패 fallback을 확인했습니다. 실제 Gemini를 호출하지 않았습니다.

## 참고한 공식 문서

- [FFmpeg 필터 — atempo, apad, atrim, concat](https://ffmpeg.org/ffmpeg-filters.html)
- [FFmpeg 명령과 인코딩](https://ffmpeg.org/ffmpeg.html)
- [Playwright Network](https://playwright.dev/python/docs/network)
- [Playwright Screenshots](https://playwright.dev/python/docs/screenshots)
- 한국어 음성은 설치된 macOS `say -v '?'`와 실제 AIFF/MP4 생성으로 확인했습니다.

## 남은 범위

Phase 3-C의 작업 큐·진행률·취소 API·UI·사용자별 저장/권한은 구현하지 않았습니다. 기존 스토리보드 API는 JSON만 반환하고 기존 shorts 선택은 제공된 샘플 영상을 유지합니다. 새 영상은 명시적 로컬 CLI로 생성합니다. Linux/Windows TTS, 폰트 패키징, TTS 단어 정렬, 임의 개념의 사실성 검토는 후속 작업입니다.
