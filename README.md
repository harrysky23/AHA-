# AHA! (아하!) · Remotion 렌더러 추가


## Claude 기반 범용 학습 숏츠

`AHA_VIDEO_RENDERER=claude`를 설정하면 기존 숏츠 폼과 `/api/videos` 작업 큐에서 새 경로를 사용합니다. ChatKHU의 Claude가 장면별 한국어 대본과 중앙 시각화 TSX를 직접 작성합니다. 기존 React 화면이 브랜드·제목·자막을 렌더링하고, 기존 ChatKHU TTS의 음성을 FFmpeg로 결합합니다. 기본 출력은 1080×1920·30fps H.264/AAC입니다. 기존 `svg` 기본값과 `remotion` 선택도 사용할 수 있습니다.

```bash
docker build -t aha-remotion-isolated:1 video-remotion
AHA_VIDEO_RENDERER=claude .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --workers 1
```

`.env`의 ChatKHU 인증·TTS 설정을 사용합니다. `VIDEO_CODE_MODEL`과 `VIDEO_REPAIR_MODEL`의 기본값은 모두 `claude-opus-5-5`입니다. 이 모드의 숏츠 폼에서 PDF, PNG/JPEG/WebP, UTF-8 TXT를 첨부할 수 있습니다. API의 `material_text` 필드에도 참고 텍스트를 입력할 수 있습니다. 첨부 이미지 자체는 Claude의 참고 입력으로 전송됩니다. 동의 화면에서 전송과 크레딧 사용을 안내합니다.

실제 코드 생성 1회와 TTS 최대 1회가 한 작업에 들어갑니다. 코드 검사나 렌더/인코딩 실패에서만 같은 대본을 유지한 채 코드 수정 1회를 시도합니다. 이미지 생성과 영상 생성 API 호출은 0회입니다. Docker 이미지 확인에 실패하면 Claude 요청 전 중단합니다. 입력·출력 토큰, 모델, 응답 시간, 반환된 차감 정보와 오류 코드는 `tmp/video-jobs/<job-id>/code-*/report.json`에 기록됩니다. 대본과 TSX는 같은 비공개 디렉터리에서 디버깅할 수 있고 웹에서 제공하지 않습니다. 작업 만료·삭제·서버 종료 시 함께 정리됩니다.

```bash
# 오프라인 호출 계획
.venv/bin/python scripts/check_claude_video.py A
# 명시적으로 승인한 첫 실계정 테스트. 수정 호출까지 승인한 경우
.venv/bin/python scripts/check_claude_video.py A --live --allow-repair
```

실계정 CLI의 결과는 `tmp/claude-video/<A|B|C>/video.mp4`에 저장합니다. API 호출은 모델·계정 정책에 따라 기존 크레딧을 차감합니다. `--allow-repair`는 수정 호출 최대 1회를 추가로 허용합니다. 한 번 승인한 검증을 반복 실행하면 다시 요청을 보내므로 결과와 작업 보고서를 먼저 확인하세요.

TSX 검증과 Remotion 실행은 비루트 Docker 컨테이너에서 이뤄집니다. 코드에는 지정된 React JSX·SVG 요소와 Remotion 훅만 허용합니다. 컨테이너 실행에는 네트워크, 호스트 비밀 파일, Docker 소켓, 쓰기 가능한 호스트 디렉터리를 제공하지 않습니다. 읽기 전용 루트와 입력, tmpfs, CPU·메모리·프로세스 수·외부 실행 시간 제한을 사용합니다. TTS는 한 번 호출한 WAV의 실제 길이와 쉼을 기준으로 장면을 구성하며 쉼을 구분하기 어려울 때는 문자 수로 근사합니다. 단어 수준의 시점은 제공하지 않습니다. [변경 목록과 검증 기록](docs/CLAUDE_VIDEO_NOTES.md).

## Remotion · 물의 순환 모션그래픽

기존 FFmpeg 렌더러와 별도로 React/TypeScript + **Remotion4.0.545** 경로를 추가했습니다. 기존 이미지·19.4초 한국어 TTS를 재사용해 증발 입자 상승 → 응결·구름 형성 → 강수 → 하천 이동 → 전체 순환을 프레임 기반으로 표시합니다. 기본 출력1080×1920/30fps/H.264+AAC, 프리뷰540×960입니다. 외부 AI 호출은 없습니다.

이번 로컬 결과는 `tmp/remotion/release/water-cycle.mp4`, 원본 복사본은 `C-original.mp4`, 나란히 보는 페이지는 `comparison.html`입니다. 원본 `tmp/chatkhu/comparison/verified-full/C.mp4`도 보존했습니다. 최종30초 영상 생성·전체 디코딩·Chrome 재생을 확인했습니다. 한국어 글꼴은 기존 macOS Apple SD Gothic Neo를 사용하고 원격 글꼴을 다운로드하지 않습니다.

```bash
# 프로젝트 루트에서. Python·Chrome·FFmpeg/macOS TTS는 기존 설치를 재사용.
npm --prefix video-remotion ci --ignore-scripts --no-audit --no-fund
npm --prefix video-remotion run typecheck
npm --prefix video-remotion test

# 승인된 기존 C 명세·이미지·WAV가 있는 이 작업 공간에서 재구현
# 출력이 이미 있으면 다른 디렉터리 지정. API 호출/새 TTS 생성 없음.
.venv/bin/python scripts/render_remotion.py --preview --fps 3 \
  --output tmp/remotion/my-preview/water-cycle.mp4
.venv/bin/python scripts/render_remotion.py --audit \
  --output tmp/remotion/my-final/water-cycle.mp4

# 기존 자산 없이도 가능한 일반 mock + macOS TTS 경로
.venv/bin/python scripts/render_storyboard.py --mock science --duration 30 \
  --renderer remotion --preview --fps 3 --output tmp/remotion/mock.mp4
# 기존 SVG/FFmpeg 경로는 그대로
.venv/bin/python scripts/render_storyboard.py --mock science --duration 30 \
  --renderer svg --preview --fps 3 --output tmp/remotion/svg.mp4
```

기존 `StoryboardSpec`과 별도로 `remotion-plan-1`에 허용된 장면 유형·제목·설명·시간·자막을 둡니다. `video-remotion/examples/water-cycle-cues.json`의 장면 시간·표시 문장을 수정하면 다음 렌더에 반영됩니다. 자막은 원본 내레이션과 일치해야 하며, 검토 큐는 원본 WAV SHA256에 묶입니다. 원본 음성에 없는 새 말을 자동으로 생성하지 않습니다. 예제는1초 도입 후 기존 WAV를 재생하고20.4초부터 복습합니다. 무음 구간을 참고해 절에 배정한 편집 가능한 큐이며, 자동 음소·단어 정렬이나 청취 검증으로 표시하지 않습니다.

일반 JSON 자동 렌더링은 기존 API 응답/StoryboardSpec + 선택적 MediaPlan/RemotionPlan을 받습니다.

```bash
.venv/bin/python scripts/render_storyboard.py --input tmp/storyboard.json \
  --renderer remotion --media-plan tmp/media-plan.json \
  --asset-root tmp/reviewed-assets --animation-plan tmp/animation-plan.json \
  --output tmp/remotion/custom.mp4
```

현재 Remotion 개념 애니메이션은 물의 순환에 한정합니다. 다른 개념·미지원 장면은 텍스트 템플릿으로 대체하고 기록합니다. 기존6종 SVG DSL은 기존 렌더러에서 계속 지원합니다. 장면 길이·자막 겹침·원문/명세/음성 해시를 검증하고 임의 코드·외부 미디어 URL을 실행하지 않습니다. 새 경로도 기존 단일 실행 잠금·worker/자식 종료·시간/용량 제한·임시파일 정리·MP4 검사를 공유합니다. 실제 진행 프레임 수를 기존 웹 UI에 전달합니다.

### Studio 미리보기

```bash
.venv/bin/python scripts/render_remotion.py --prepare-studio \
  --output tmp/remotion/studio/water-cycle.mp4
npm --prefix video-remotion run studio -- --props ../tmp/remotion/studio/studio-props.json
# 표시된 localhost:3100에서 확인. 종료 Ctrl+C.
```

`--prepare-studio`는 검토된 예제 배경·음성을 `video-remotion/public/generated/`로 복사합니다. 이 폴더와 tmp는 Git에서 제외됩니다. Studio는 개발 서버이므로 민감한 학생 자료를 복사하지 마세요. 생성된 `--props` 파일을 수정하거나 cue JSON으로 다시 준비합니다. 이 입력은 Studio의 기본 props보다 우선합니다. `AHA!`의 느낌표가 Webpack과 충돌하므로 래퍼는 예약 문자가 없는 임시 별칭을 사용합니다. 원본 프로젝트명은 바꾸지 않습니다.

### 기존 웹 API에서 사용

```bash
# .env를 직접 바꾸지 않고 해당 서버 프로세스에만 선택 적용
AHA_AI_PROVIDER=mock AHA_VIDEO_RENDERER=remotion \
AHA_VIDEO_PREVIEW=true AHA_VIDEO_FPS=3 \
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766 --workers 1 --no-access-log
```

`POST /api/videos`와 기존 폼·상태·취소·소유권·Range 재생 API를 그대로 사용합니다. 웹 입력은 기존 자료 분석/스토리보드와 macOS TTS를 사용하며, 운영자 검토 자산을 자동으로 선택하거나 새 ChatKHU 미디어를 호출하지 않습니다. 기본 `AHA_VIDEO_RENDERER=svg`이며 서버 재시작으로 선택을 변경합니다. Gemini를 선택하면 기존 동의·자료 전송·API 사용량 정책은 적용됩니다.

### 검증과 라이선스

```bash
.venv/bin/python -m pytest -q
.venv/bin/python tests/check_remotion_output.py tmp/remotion/release
.venv/bin/python tests/browser_rendered_videos.py tmp/remotion/release
# 위 mock/Remotion 서버에서 실제 웹 생성·취소 검사
AHA_BASE_URL=http://127.0.0.1:8766 .venv/bin/python tests/browser_phase3c.py
```

Remotion4.0.545, React19.2.4, TypeScript5.9.3을 package-lock으로 고정했습니다. Remotion은 일반 MIT 라이브러리로 간주하면 안 됩니다. 설치된 LICENSE와 [공식 조건](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)은 개인·3인 이하 영리 조직·비영리 조직·비상업적 도입 평가 등에 무료 자격을 부여합니다. 자격 밖의 운영에는 Company License가 필요합니다. 이번 구현은 로컬 도입 평가이며 자동 구매·과금 등록을 하지 않았습니다. 실제 조직·상업 서비스 적용 전 해당 조건을 확인해야 합니다. [공식 렌더링 문서](https://www.remotion.dev/docs/renderer/render-frames), [개발 기록과 실제 비교](docs/REMOTION_NOTES.md).

## Phase 3-D · 승인형 멀티모달 영상 합성

ChatKHU 이미지·영상·한국어 TTS Provider를 구현하고 각각 승인된 실제 생성1회를 검증했습니다. 기존 StoryboardSpec에 별도 `MediaPlan`을 연결해 로컬 AI 이미지·영상·음성과 SVG·자막을 FFmpeg로 합성합니다. 물의 순환 A/B/C 비교 결과는 `tmp/chatkhu/comparison/verified-preview/`와 `verified-full/`에 저장합니다. 기존 Gemini HTML/스토리보드와 Phase 3-C 웹은 유지하며, 웹 작업은 계속 로컬 SVG/TTS를 사용합니다. ChatKHU 과금 생성은 별도 승인형 CLI에서만 실행합니다.

```dotenv
CHATKHU_API_KEY=로컬에서만_설정
CHATKHU_BASE_URL=https://factchat-cloud.mindlogic.ai/v1/gateway
CHATKHU_IMAGE_MODEL=gemini-3.1-flash-lite-image
CHATKHU_VIDEO_MODEL=fal-ai/kling-video/v3
CHATKHU_TTS_MODEL=gemini-3.1-flash-tts-preview
```

```bash
# 기본은 계획 출력만 수행. 키 값 대신 존재 여부만 표시하고 네트워크 미사용.
python scripts/check_chatkhu.py --kind image
python scripts/check_chatkhu.py --kind tts
python scripts/check_chatkhu.py --kind video # 이미지 검토 전이면 대기 안내
python -m pytest tests/test_chatkhu.py -q    # HTTP 대역; 실제 모델 호출 없음
```

공식 세부 문서를 확인한 Bearer 인증과 요청/응답만 구현했습니다. 승인된 모델/견적 조회와 이미지1회·영상1회·TTS1회 생성 경로를 검증했습니다. 이 검증에 대한 추가 호출은 승인되지 않았습니다. 다음 명령은 **별도로 승인한 뒤** 사용하세요.

```bash
# 생성하지 않는 사전 조회: 모델 GET1건 + 공식 무료 견적 POST1건
python scripts/check_chatkhu.py --kind image --preflight
# TTS --preflight는 모델 GET1건만. 공식 /estimate는 TTS 미지원.

# 아래는 실제 과금 가능. 모델·본문 해시·비용을 보고 사용자 승인 후에만 실행.
# REQUEST_HASH는 plan.json의 request_hash. 이 문서만으로 호출이 승인되지는 않음.
python scripts/check_chatkhu.py --kind image --live \
  --approval-hash REQUEST_HASH \
  --quote-file tmp/chatkhu/image/preflight.json --accept-unknown-cost
```

`--accept-unknown-cost`는 이미지 견적이 minimum이거나 TTS 비용이 미확정인 경우 사용자가 최종 금액 상한 미확정을 다시 승인했을 때만 지정합니다. 크레딧 하드 상한을 강제하는 옵션이 아닙니다. 사전 견적은 같은 요청의 최근1시간 기록만 받습니다. 생성은 종류별 최대1회이며 오류/타임아웃도 시도1회를 소비한 것으로 취급합니다. 자동 재시도·유료 모델 전환·이미지 실패 후 텍스트 영상 자동 대체는 없습니다.

이미지 결과를 검토한 다음 `--kind video --input-image tmp/chatkhu/image/asset-....png`로 영상 계획을 만듭니다. 원본 이미지의 디코딩·크기와 해시까지 승인 범위에 포함합니다. Kling은3초/standard/오디오 제외, Seedance2.0은5초/720p를 사용합니다. 해당 모델 문서에 없는 해상도·말투 필드는 전송하지 않습니다. 영상의 텍스트 전용 검증은 별도로 승인한 `--text-only`만 가능합니다.

비동기 요청은 operation_id를 `pending-operation.json`에 먼저 저장하고 제한 시간 동안 조회합니다. 시간 초과/연결 실패 때 생성 요청을 반복하지 마세요. 같은 모델과 작업 ID로 GET만 재개할 수 있습니다.

```bash
python scripts/check_chatkhu.py --kind video \
  --resume tmp/chatkhu/video/pending-operation.json
```

결과는 `tmp/chatkhu/`에 검증한 로컬 PNG/JPEG/WebP/MP4/WAV와 `result.json`, 시도별 `run-*.json`으로 저장합니다. 재개 기록은 최초 시도 기록을 가리킵니다. `credits_charged`·JSON billing·TTS X-Billing/토큰 헤더의 공식 응답 값만 기록하며 없는 사용량은 unknown으로 둡니다. 폴링 응답에 같은 차감액이 반복될 수 있으므로 이벤트를 합산해 실제 비용으로 표시하지 않습니다. 응답에 포함되지 않은 조직 콘텐츠 검사 비용은 대시보드로 따로 확인해야 합니다.

결과 URL은 렌더러에 전달하지 않습니다. 인라인 이미지는 디코딩하고, 문서의 Gateway 다운로드 경로 또는 허용된 `fal.media` HTTPS CDN에서 인증 정보를 분리해 복사합니다. 다른 호스트·리다이렉트는 자동 접근하지 않습니다. 크기·길이·코덱·전체 디코딩 검사 후 로컬 파일만 반환합니다. CDN URL 수명은 공식 문서에서 확인하지 못했으므로 보장하지 않습니다. 공개된 기본 단가는 계정별 견적이나 최종 비용과 같다고 보장할 수 없습니다.

문서 출처·실제 생성 결과·비교·제약은 [Phase 3-D 기록](docs/PHASE3D_NOTES.md)에 정리했습니다. 이미지 API 보고 차감34.21cr,영상252cr,TTS는 입력76/출력485토큰이며 공식 차감액 미반환입니다. PCM24kHz/mono 한국어 음성19.4초를 검증했습니다. AI 원본의 잘못된 라벨·화살표가 있는 중앙 영역을 제외하고 배경으로만 사용하며, 정확한 과정은 SVG가 표시합니다. 발음·억양의 청취 평가는 별도 필요합니다.


### 승인된 파일로 합성하기 · 네트워크 미사용

```bash
# 같은 주제·30초 명세로 A:SVG, B:이미지+SVG, C:이미지+영상+TTS 비교
# 기존 승인 결과 result.json과 로컬 파일이 필요. 파일 누락 시 SVG/로컬 음성.
python scripts/compare_water_cycle.py --output tmp/chatkhu/comparison/new-preview --preview --fps 3
# 기본 1080×1920, 30fps. 기존 출력은 덮어쓰지 않음.
python scripts/compare_water_cycle.py --output tmp/chatkhu/comparison/new-full --fps 30

# Gemini /api/storyboard 응답도 같은 StoryboardSpec 입력으로 사용 가능
python scripts/render_storyboard.py --input tmp/storyboard.json \
  --media-plan tmp/media-plan.json --asset-root tmp/reviewed-assets \
  --output tmp/videos/multimodal.mp4 --preview --fps 3
python -m pytest tests/test_chatkhu.py tests/test_multimodal.py -q
python tests/browser_multimodal.py
python tests/browser_rendered_videos.py tmp/chatkhu/comparison/verified-preview
```

`create_media_plan()`은 명세 해시와 scene_id에 계획을 묶습니다. 모드는 `svg_animation`, `ai_image`, `ai_image_motion`, `ai_video`, `text_motion`이며 수학 그래프·알고리즘은 SVG가 우선입니다. `LocalMedia`에는 파일명·SHA256·검토 상태만 허용합니다. 외부 URL·경로·실행 코드는 받지 않습니다. 운영자 검토가 필요한 계획이므로 LLM의 자체 승인 값을 신뢰해 공개하지 마세요. `propose_visual_requests()`는 기존 Gemini 명세로 일관된 이미지 요청 계획만 만들며 호출하지 않습니다. 이미지 검토 후 영상 요청·견적·승인은 별도로 진행합니다.

동일 자산을 여러 장면·A/B/C에서 해시로 확인해 재사용합니다. 새 합성에는 API 호출0회입니다. 누락·해시 불일치·디코딩 실패·검토 거절·합성 오류는 장면별 SVG 대체 사유로 기록하고, 외부 음성의 원문 해시가 맞지 않거나 길이가 과하면 macOS 음성으로 대체합니다. 시간·디스크·취소 오류는 중단하며 제한을 우회하지 않습니다. 원본 영상 소리는 쓰지 않고 짧은 배경 클립만 반복합니다. 외부 음성 자막은 측정된 길이에 글자 수로 배분한 근사 정렬이며 단어 단위 정렬이 아닙니다. 음성 종료 후 복습 문장을 표시합니다. 실패한 유료 생성 CLI는 오류를 알리고 멈추며, 기존 SVG 생성은 계속 이용할 수 있습니다.

MediaPlan·자산은 worker 임시 폴더로 복사해 기존 시간/디스크/단일 실행/취소 정책 안에서 처리합니다. 미디어당100MiB·복사 합계256MiB, 원본 이미지/영상4096px·영상60초·외부 음성120초 상한이며 worker에 API 키를 전달하지 않습니다. 물의 순환 `requires_mask` 결과는 검토한 상단30%·하단20%만 합성하고 중앙을 제외합니다. 다른 자산에 이 크롭이 안전하다고 자동 판정하지 않습니다.

기존 랜딩·수학·사회 데모를 유지하고 FastAPI에 **자료 업로드 → 질문 → 학습 방식 → JSON 학습 명세 → 인터랙티브 학습**을 연결했습니다.

웹의 인터랙티브 학습은 Gemini 모드에서 입력한 주제별 실습을 생성합니다. mock 모드에서는 수학 II의 **f(x)=x², a=1에서 할선→접선·미분계수** 예제를 엽니다. Phase 3-C의 숏츠는 별도 경로로 동작하며 자료와 질문을 바탕으로 MP4 생성 상태, 재생, 다운로드를 제공합니다.

## Phase 3-C · 웹에서 숏츠 만들기

먼저 아래 Phase 3-B 항목의 로컬 음성·Chrome/Chromium·FFmpeg 의존성을 준비하세요. `.env`의 Gemini 키를 그대로 보존하며 설정 예시는 `.env.example`에 있습니다.

```bash
source .venv/bin/activate
python -m pip install -r requirements-render.txt

# 개발·심사용: 실제 AI 호출 없이 mock 스토리보드 + 실제 한국어 MP4
AHA_AI_PROVIDER=mock AHA_VIDEO_PREVIEW=true AHA_VIDEO_FPS=3 \
  python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766 --workers 1

# .env의 Gemini 설정으로 실행. 사용자가 동의한 새 작업만 실제 AI를 호출합니다.
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --workers 1
```

접속 후 개념·질문과 선택적인 PDF를 입력하고 **숏츠 학습**을 고릅니다. 설명 수준과30/45/60초를 선택해 생성합니다. Gemini 모드에서는 Google 전송 동의가 필수이며 기존 무료 티어·성인 평가용 제한은 아래 안내와 동일합니다. mock은 미분계수·물의 순환·수요와 공급·이진 탐색 예제를 실제로 렌더링합니다. mock 성공을 AI 생성 성공으로 표시하지 않습니다.

UI는 자료 분석·영상 구성·음성/애니메이션·인코딩·검사·완료를 표시합니다. 프레임 수는 worker가 기록한 실제 캡처 수이며 전체 진행 퍼센트나 완료 예상 시간은 제공하지 않습니다. 실패하면 구성/렌더링 단계와 오류 코드를 표시하고 재시도·기존 예시 영상 보기를 제공합니다. 새 영상은9:16 플레이어에서 재생하고 MP4로 다운로드할 수 있습니다. 기존 인터랙티브 학습과 원본 데모는 유지합니다.

| API | 동작 |
| --- | --- |
| `POST /api/videos` | multipart 입력 검증 후202 + job_id. PDF 분석·AI·렌더링 완료를 기다리지 않음 |
| `GET /api/videos/{job_id}` | queued/generating/rendering/completed/failed/cancelled, stage, 실제 progress, error, 만료 시각. 완료 시 video_url |
| `GET /api/videos/{job_id}/file` | 소유권과 완료 상태 확인 후MP4만 제공. Range206/416·스트리밍·`?download=1` 지원 |
| `DELETE /api/videos/{job_id}` | 대기 작업 즉시 취소. 실행 중이면202 + cancel_requested, 실제 종료·정리 후 cancelled. 완료 영상은 삭제 |

입력은 `concept`(200자), `question`(2000자), 선택적 `file`(기존5MiB 제한), `consent=true`(Gemini 필수), `student_level`(foundation/high_school/advanced), `target_duration_seconds`(30–60 정수, 기본45)입니다. 기존 폼의 `format=shorts`도 허용합니다. `/api/learn`의 기존 샘플 영상 응답과 `/api/storyboard`의 JSON 응답은 호환성을 유지합니다.

```bash
# mock 서버 예시. cookie jar도 비밀 값이므로 tmp/ 밖으로 공유하지 마세요.
curl -c tmp/video-cookies.txt -X POST http://127.0.0.1:8766/api/videos \
  -F 'concept=물의 순환' -F 'question=증발과 응결의 연결을 설명해 주세요.' \
  -F 'target_duration_seconds=30' -F 'student_level=high_school'
curl -b tmp/video-cookies.txt http://127.0.0.1:8766/api/videos/JOB_ID
curl -b tmp/video-cookies.txt -H 'Range: bytes=0-31' \
  http://127.0.0.1:8766/api/videos/JOB_ID/file
curl -b tmp/video-cookies.txt -X DELETE http://127.0.0.1:8766/api/videos/JOB_ID
```

작업 소유권은 서버가 발급한256bit 임의 쿠키로 확인합니다. HttpOnly·SameSite=Strict이며 HTTPS에서는 Secure, 경로는 `/api/videos`, 쿠키 수명은24시간입니다. 서버는 소유자 해시만 저장하고 job_id만 아는 다른 세션에는 상태·파일·삭제 모두404를 반환합니다. 토큰을 URL·localStorage·일반 로그에 넣지 않습니다. 변경 요청의 다른 Origin/cross-site도 거절합니다. 이는 로컬 PoC용 익명 세션이며 사용자 계정 인증이나 인터넷 공개 서비스의 권한 체계를 대신하지 않습니다.

**복구·취소·삭제 정책:** 브라우저를 닫아도 작업은 계속되며 localStorage에는 질문/자료 없이 마지막 job_id만 저장합니다. 같은 origin·쿠키로 다시 열면 작업을 조회합니다. 다른 브라우저·쿠키 삭제·만료 시에는 복구할 수 없습니다. 서버 상태는 메모리이므로 **서버 재시작·종료 시 모든 작업과 웹 영상은 폐기**하며 이전 ID는404입니다. 정상 종료는 실행 작업의 취소를 기다린 뒤 정리하고, 갑작스러운 부모 종료는 worker watchdog이 자식까지 종료합니다. 다음 시작에서 전용 저장소의 이전 작업 폴더를 제거합니다. CLI 영상 폴더는 건드리지 않습니다.

취소 요청을 받았다는 이유만으로 cancelled로 바꾸지 않습니다. 취소 신호를 렌더러에 전달하고 worker 및 분리된 Chrome 자식을 PID/생성 시각으로 추적해 종료·정리한 뒤 확정합니다. 종료 확인 실패는 `cleanup_failed`입니다. 완료와 취소가 경합하면 서버 루프에서 먼저 반영된 순서대로 처리하며, 취소가 요청된 결과는 공개하지 않습니다. 이미 시작된 소유자의 다운로드는 끝날 수 있고 파일은 마지막 스트림이 끝난 후 삭제합니다.

| 환경변수 | 기본값·범위 |
| --- | --- |
| AHA_VIDEO_QUEUE_LIMIT | 대기3개,1–8 |
| AHA_VIDEO_MAX_JOBS | 전체 기록16개,대기 한도+1 이상·최대64 |
| AHA_VIDEO_TTL_SECONDS | 생성 시점부터3600초,120–7200. 완료·실패·취소 기록에도 적용 |
| AHA_VIDEO_RUN_SECONDS | 시작 후 전체 처리900초,10–1800 |
| AHA_VIDEO_STORAGE_MB | 전용 저장소2048MiB,512–4096. 다음 렌더링 예산을 확보할 수 없으면 거절 |
| AHA_VIDEO_PREVIEW | false(1080×1920). true이면540×960 |
| AHA_VIDEO_FPS | 30,1–30. 개발 검증 권장3 |
| AHA_VIDEO_RENDER_TIMEOUT_SECONDS | Phase 3-B 렌더러600초,10–1800 |
| AHA_VIDEO_MAX_DISK_MB | Phase 3-B 작업별512MiB,1–2048 |

실행기는1개이며 한 세션에서 동시에2개까지만 접수합니다. 기존 전역 렌더 잠금이 CLI에 잡혀 있으면 AI를 재호출하지 않고 제한 시간 안에서 기다립니다. 대기열/기록 한도는429, 저장 공간 부족은507입니다. 실패·취소 기록은 전체 기록 한도에 도달하면 먼저 제거될 수 있습니다. 전용 저장소는 `tmp/video-jobs`(권한0700)이고 static으로 공개하지 않습니다. 브라우저 임시 프로필도 작업 폴더 안에 둬 용량 제한·정리에 포함합니다. 이 설정은 서버 시작 때 읽으므로 변경하려면 재시작해야 합니다.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q                     # 기본 mock/HTTP 대역, 실제 Gemini/MP4 미실행
AHA_BASE_URL=http://127.0.0.1:8766 python tests/browser_phase3c.py
# 위 브라우저 검증만 실제 로컬 TTS·MP4 생성/취소. 서버는 반드시 mock이어야 함
```

프로세스 종료 검증에는 macOS의 자식 프로세스 조회 권한이 필요합니다. 제한된 실행 환경이 이를 거절하면 `process_tracking_denied`로 렌더링을 시작하지 않습니다. 실제 웹 검증 결과·경쟁 상태 테스트·남은 범위는 [Phase 3-C 기록](docs/PHASE3C_NOTES.md)을 참조하세요.

## Phase 3-B · 로컬 학습 영상 렌더링

macOS의 로컬 `Yuna` 음성, Chrome 또는 Playwright Chromium, FFmpeg/ffprobe가 필요합니다. 영상·TTS 유료 API를 호출하지 않으며 렌더링 스크립트는 `.env`를 읽지 않습니다. 아래는 독립 CLI 엔진의 실행 방법이며 웹 작업은 위 Phase 3-C 경로를 사용합니다.

```bash
source .venv/bin/activate
python -m pip install -r requirements-render.txt
brew install ffmpeg
# 설치된 macOS Google Chrome을 자동 선택합니다. 없으면:
python -m playwright install chromium
# 한국어 음성 확인. 설치된 Yuna가 없으면 macOS 음성 설정에서 준비하세요.
say -v '?' | rg 'Yuna|ko_KR'

# 개발용: 실제 외부 AI 호출 없이 예제4개, 각각45초 MP4
python scripts/render_storyboard.py --all-mocks --preview --fps 3 --output tmp/videos/my-run

# 기본 출력: 1080×1920, 30fps, H.264 + AAC
python scripts/render_storyboard.py --mock math --output tmp/videos/math-full.mp4

# /api/storyboard 응답 전체 또는 응답의 storyboard 객체를 파일로 저장한 뒤:
python scripts/render_storyboard.py --input tmp/storyboard.json --preview --fps 6 --output tmp/videos/custom.mp4
```

입력 파일은 최대128KiB이며 `StoryboardSpec`을 다시 검증합니다. 예제는 math/science/social/cs이고 `--duration 30..60`은 mock 길이만 설정합니다. 실제 Gemini 스토리보드를 원하면 앞 단계의 명시적 생성 절차를 거친 JSON을 사용하세요. 렌더러는 생성 API를 대신 호출하지 않습니다.

출력 옆의 `*.render.json`에 코덱·길이·해상도·오디오 트랙, 장면별 발화 길이와 속도 조정, 대체 장면과 원인, 파일 해시를 기록합니다. 실패는 `code/message/scene_id` JSON을 stderr로 반환하며 원문 질문·내레이션·API 키·도구 stderr는 로그로 내보내지 않습니다. 기존 출력은 덮어쓰지 않습니다. `tmp/`의 영상·기록·프레임은 Git에서 제외합니다. 사용자가 별도 출력 경로를 지정할 때도 생성 파일을 직접 커밋하지 마세요.

| 정책 | 구현 |
| --- | --- |
| 시각화 | DSL 6종. 다항식 계수·노드·타임라인·비교·명시적 상태·텍스트만 해석 |
| 대체 | 겹치는 노드·밀집 타임라인·과도한 글자 등은 `text_explanation`으로 바꾸고 장면 ID/원인을 기록. 미지 타입·코드 필드는 입력 검증에서 거절 |
| 모션 | 명시적 시점으로 계산하는 페이드·이동·확대·강조, 고정 장면 경계. 실제 시간·랜덤·CSS 애니메이션에 의존하지 않음 |
| 텍스트 | 제목/그림/주석/자막 영역 분리, 한국어 줄바꿈·축소·분할 표시. `textContent`만 사용하며 수식도 평문 |
| TTS | macOS `say` Yuna,185wpm. 교체 가능한 `TTSEngine` 인터페이스. 실패하면 무음 영상으로 숨기지 않고 오류 |
| 음성 길이 | 짧으면 장면 끝까지 무음, 길면 최대1.35배 `atempo`. 더 길면 `narration_too_long` + 장면 ID. 발화를 자르거나 장면 시간을 변경하지 않음 |
| 자막 | 문장을 분할해 장면 시간에 비례 표시. 음소/단어별 강제 정렬은 미구현 |
| 영상 | 기본1080×1920/30fps, `--preview` 540×960, `--fps 1..30`. H.264/yuv420p + AAC48kHz mono, faststart |
| 프리뷰 비용 | 재현성을 위해 캡처는1080×1920으로 고정하고 FFmpeg에서 축소. 개발 비용은 우선 낮은 FPS로 줄임 |
| 제한 | 사용자별 로컬 파일 잠금으로 동시1개, 기본600초(최대1800초), 임시 파일 합계512MiB(옵션으로최대2GiB), 여유 공간256MiB 이상 |
| 정리 | 별도 worker와 자식 프로세스 그룹 종료, 임시 디렉터리 자동 정리, 성공 검증 후에만 MP4 공개. 파일당 OS 용량 제한과 부모의100ms 용량 감시 병행 |
| 격리 | 새 비영구 브라우저 프로필, offline·모든 요청 차단·WebSocket 차단·service worker 금지·CSP. 도구에 API 키를 상속하지 않고 shell=False로 실행 |

렌더링은 장면의 폰트·템플릿·브라우저 환경을 고정한 로컬 작업입니다. macOS에서는 네트워크 없이 시스템 `Apple SD Gothic Neo`를 사용하고 AHA!의 보라·노랑·분홍 팔레트를 재사용합니다. 원본 Google Fonts를 원격으로 받지 않습니다. 브라우저/OS/설치 폰트가 달라도 동일 파일 해시를 보장하는 것은 아니며, 브라우저 설정만으로 OS 보안 격리를 완성했다고 주장하지 않습니다.

원문 자료와 인용의 의미·전체 사실성은 렌더링 검증 대상이 아닙니다. PDF 인용 일치는 Phase 3-A 생성 서비스에서 확인하며 렌더러는 DSL·시간·참조를 검사합니다. 기존 `/api/learn`과 `/api/storyboard`는 그대로이며, 스토리보드 API의 `rendering.status=not_implemented`는 **그 API에서 렌더링을 실행하지 않는다**는 기존 응답을 유지한 것입니다. 웹 생성·취소·다운로드는 별도 `/api/videos`를 사용합니다.

```bash
python -m pytest -q                  # mock/HTTP 대역; AI·영상 생성 없음
python tests/browser_rendering.py    # 6종 실제 프레임, 재현성·대체·네트워크·긴 문장
python tests/browser_rendered_videos.py tmp/videos/my-run # 생성된 예제 MP4의 Chrome 로드·탐색·재생
# 실제 생성 명령을 실행한 뒤 수동 확인도 가능:
ffprobe -v error -show_streams -show_format -of json tmp/videos/my-run/math.mp4
ffmpeg -nostdin -v error -xerror -i tmp/videos/my-run/math.mp4 -f null -
ffmpeg -nostdin -v error -ss 5 -i tmp/videos/my-run/math.mp4 -frames:v 1 tmp/math-frame.png
```

렌더링 엔진은 모든 결과에 대해 ffprobe 형식 검사와 **전체 영상·오디오 디코딩**을 수행합니다. 개발 기록과 실제 예제 위치는 [Phase 3-B 기록](docs/PHASE3B_NOTES.md)을 참조하세요.

## 현재 Provider

| 값 | 동작 |
| --- | --- |
| `mock` | HTML은 고정 수학 II 예제, 스토리보드는 개념별 템플릿. 키·외부 호출 없이 작동 |
| `gemini` | Gemini Developer API의 실제 `generateContent` 호출. 질문·추출 텍스트로 JSON 명세 생성 |
| `elice` | 별도 준비 구현체. 실제 사양 확정 전에는 네트워크 호출 없이 연결 예정 오류 반환 |

기본 모델은 **`gemini-3.5-flash-lite`**이며 `GEMINI_MODEL`로 바꿀 수 있습니다. 실제 생성 2건과 FastAPI·PDF·그래프·캐시 재사용을 검증했습니다. 처음 지정했던 2.5 모델의 404와 3.5의 일시적 503도 기록했습니다. 상세 결과는 [Phase 2 기록](docs/PHASE2_NOTES.md)을 참조하세요. HTTP 대역 테스트는 실제 AI 생성 성공으로 계산하지 않습니다.

## Phase 3-A · 범용 스토리보드 JSON

`POST /api/storyboard`를 추가했습니다. 기존 `/api/learn`의 HTML·기존 영상 응답과 프론트엔드는 유지합니다. 새 API는 `StoryboardSpec(schema_version=storyboard-1)`을 반환하며 `LessonSpec`과 분리되어 있습니다. 이번 단계는 스토리보드만 만들며, 영상이나 음성 생성 완료로 표시하지 않습니다.

지원 시각화는 function_graph / process_diagram / timeline / comparison / state_transition / text_explanation입니다. 함수는 최대3차 계수·좌표만 받고 임의 수식 코드는 실행하지 않습니다. 그림은 제한된 노드·연결·좌표·동작 데이터만 받습니다. [DSL과 렌더러 계약](docs/STORYBOARD_DSL.md)에 각 파라미터·상한·시간 해석을 정리했습니다.

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
3. 원하는 개념이나 질문을 입력하고 **인터랙티브 학습**을 선택합니다. 예를 들어 “빛을 흡수한 뒤 광합성에서 어떤 일이 일어나나요?”를 입력할 수 있습니다.
4. Gemini 모드에서는 전송 안내를 확인합니다.
5. 만들어진 설명을 읽고 그래프 슬라이더, 단계·사건 탐색, 비교 기준 선택 등 주제에 맞는 실습과 확인 문제를 풉니다. 시각화로 표현하기 어려운 개념은 설명 카드와 확인 문제를 엽니다. 같은 입력을 다시 제출하면 캐시를 재사용합니다.
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
- 429는 할당량/요청·토큰 제한을 의미합니다. 웹의 범용 인터랙티브 경로는 Gemini가 모델 과부하(503)를 알린 경우에만 같은 모델로 최대 한 번 재시도하며 최초 요청과 제한 시간을 공유합니다. Gemini가 5초를 초과하는 대기 시간을 안내하면 해당 요청은 바로 종료하고 대기 시간을 응답에 포함합니다.
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

범용 학습 명세에는 학습 목표, 설명, 실습 안내, 시각화, 확인 문제, 자료 인용과 참고 사항이 들어갑니다. Gemini는 질문에 맞춰 다항식 그래프, 과정, 타임라인, 비교, 상태 변화, 설명 카드 중 하나를 선택합니다. Gemini에 보내는 스키마는 구조와 필드 타입을 지정하고, 배열 길이와 숫자 범위는 서버 검증에서 적용합니다. 그래프는 3차 이하의 계수와 좌표로 정의하며, 브라우저에서 슬라이더에 따른 값을 계산합니다. 인용은 제공된 페이지의 추출 문자열과 비교합니다. 자연어 설명과 확인 문제의 정확성은 자료와 함께 검토해야 합니다.

기존 미분계수 전용 명세의 `secant_tangent_x2`는 기존 API와 고정 예제에서 계속 사용할 수 있습니다. 함수·기준점·범위는 고정되며 h≠0의 할선 기울기 2+h, 접선 기울기 2, h=0 미정의를 코드로 검증합니다.

뷰어는 고정 스크립트 해시 CSP와 `sandbox="allow-scripts"` iframe을 사용합니다. 검증된 JSON을 전달하고, 모델이 반환한 문자열은 `textContent`로 표시합니다.

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
| 수학·인용·스키마 | `invalid_interactive_spec` 또는 기존 `invalid_lesson_spec` |
| Elice 선택 | `elice_not_implemented`, 네트워크 호출 없음 |

`GET /api/health`는 모드·설정 형식 확인·캐시 여부·제한 시간을 반환합니다. `ai_configured=true`는 실제 인증·생성 성공을 뜻하지 않습니다.

`POST /api/learn`은 multipart이며 `concept`(200자), `question`(2,000자), `format=interactive|html|shorts`, 선택적 `file`, Gemini의 `consent=true`를 받습니다. 개념·질문 중 하나가 필수입니다. `interactive`는 Gemini 기반 범용 실습, `html`은 기존 미분계수 학습 명세, `shorts`는 기존 영상 예시입니다. 전송 확인은 캐시 조회 전에도 요구합니다.

```bash
curl http://127.0.0.1:8765/api/health
curl -X POST http://127.0.0.1:8765/api/learn \
  -F 'question=광합성에서 빛 에너지는 어떻게 쓰이나요?' \
  -F 'format=interactive' -F 'consent=true'
```

응답은 `mode`, 입력, 자료 처리 상태, `generation`(Provider·모델·요청 ID·캐시·토큰), `verification`, `lesson.spec` 또는 기존 영상입니다. 앱 로그에는 요청 ID·모드·상태·오류 코드만 기록합니다. 일반 오류 응답에는 Google이 반사할 수 있는 원문을 포함하지 않습니다.

## 테스트와 실제 검증

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_api.py tests/test_phase2.py tests/test_interactive.py tests/test_providers_cache.py -q
python -m pytest tests/test_storyboard.py -q
# 기존+신규 전체 검사:
python -m pytest -q
node --check frontend/static/workflow.js
```

일반 테스트는 mock·HTTP 대역을 사용하며 실제 API를 호출하지 않습니다. 기존 데모, 주제별 실습 명세, 키 비노출, PDF 인용, Gemini 요청·실패, 검증·캐시와 렌더링·작업 정책을 확인합니다. 일부 프로세스 제어 테스트는 무해한 실제 대역 프로세스를 생성·종료합니다. ChatKHU 검사는 합성 PNG/PCM 파일의 로컬 디코딩을 수행합니다.

Phase 3-A의155개에 Phase 3-B의 렌더링 정책·음성 길이·시간/디스크 제한·실패 정리·키 상속 방지 검사를 추가했습니다. 실제 브라우저·TTS·MP4 검증은 위 명시적 명령으로 분리하며 일반 pytest에서 실행하지 않습니다.

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

실제 FastAPI·PDF·브라우저 그래프와 캐시까지 한 번에 확인하려면 Gemini 서버를 실행한 상태에서 `python tests/browser_live_gemini.py`를 실행합니다. 이 검증은 합성 자료로 학습을 생성하고 같은 입력의 캐시 hit를 확인합니다. 첫 제출의 외부 API 호출은 캐시 hit면 0회, 생성 시 일반적으로 1회, Gemini 모델 과부하로 재시도하면 최대 2회이며 실제 할당량을 사용합니다. 일반 테스트에는 포함되지 않습니다.

## 소스 구조

```text
backend/app/
  config.py                 서버 환경 설정
  providers/
    base.py, __init__.py     공통 계약·Provider 선택
    mock.py                 고정 예제
    gemini.py               Google generateContent
    chatkhu/                별도 승인형 이미지·영상·TTS Provider와 로컬 미디어 검증
    elice.py                네트워크 없는 준비 구현체
  schemas.py                학습 명세·수학·인용 검증
  storyboard_schema.py     별도 범용 영상 DSL·시간·참조 검증
  rendering/               검증된 HTML/SVG 프레임·로컬 TTS·FFmpeg·제한/worker
    assets/                소유한 scene.html/css/js; 모델 코드를 받지 않음
  services/
    lessons.py              PDF → Provider → 검증 → 캐시 → 응답
    prompts.py              버전이 있는 프롬프트
    validation.py           공통 JSON 검증
    cache.py                메모리 TTL/LRU·동시 요청 공유
    materials.py, pdf_worker.py
    storyboard*.py          스토리보드 생성·mock·독립 프롬프트·검증
    uploads.py              기존·신규 API의 공통 파일 검증
    storyboard_input.py     스토리보드/영상 API의 공통 multipart 검증
    video_jobs.py           제한된 비동기 대기열·상태·취소·만료·파일 lease
  video_config.py           웹 영상 정책·렌더링 옵션
  routes/storyboard.py      POST /api/storyboard
  routes/videos.py          생성/조회/취소/소유권 검증 파일 스트리밍
frontend/                   기존 랜딩·폼·격리된 그래프
frontend/static/video-jobs.js 생성 작업 폴링·복구·취소·세로형 플레이어
scripts/prepare_frontend.py  원본 + 폼으로 실행 HTML 재구성
scripts/check_gemini.py      명시적 실제 호출 검증
scripts/check_storyboard.py  기본 mock / 명시적 --live 스토리보드 검증
scripts/render_storyboard.py 로컬 JSON/mock → 실제 MP4; 외부 API 호출 없음
tests/                      회귀·Provider·캐시·브라우저 검증
references/                 보존한 HTML·기획 PDF
```

`frontend/workflow.html`을 수정하면 `python3 scripts/prepare_frontend.py`로 index를 재구성합니다. index 직접 수정은 재구성 시 덮어씁니다. 원본 Google Fonts 링크는 유지하며 연결이 없으면 시스템 글꼴을 사용합니다. 로컬 변경은 아직 GitHub에 커밋·푸시하지 않았습니다.
