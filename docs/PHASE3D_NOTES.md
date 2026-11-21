# Phase 3-D · 승인형 ChatKHU 멀티모달 영상 합성

## 시작 상태와 구현 범위

2026-11-21, main의0943922에서 시작했습니다. Phase3-A StoryboardSpec/6종 DSL,3-B의 독립 로컬 렌더러,3-C의 비동기 웹 작업·소유권·취소가 있었습니다. AGENTS, 제품/구현 문서, 기존 코드와 공식 세부 문서를 확인한 뒤 이를 재사용했습니다. 원본 HTML과 Gemini 학습/스토리보드 Provider 계약은 유지했습니다.

완료 범위는 ChatKHU 이미지·영상·한국어 TTS Provider, 승인 전용 검증 도구, 별도 MediaPlan, 로컬 미디어+SVG/자막 FFmpeg 합성, 실제 물의 순환 A/B/C 비교입니다. 일반 웹 작업은 기존 SVG/macOS TTS 경로입니다. 유료 미디어는 운영자가 요청·견적·결과를 검토하는 별도 CLI로 생성합니다. 웹의 자동 과금·승인 UI는 추가하지 않았습니다.

.env의 키 존재, 공식 Base URL, 모델 설정을 확인했습니다. 키 값·인증 헤더·서명 URL 쿼리는 출력하지 않았고 환경파일도 수정하지 않았습니다. .env와 tmp 결과는 Git 제외 대상입니다. 커밋·푸시는 수행하지 않았습니다.

## 변경 파일과 연결 방식

- providers/chatkhu/settings.py: 서버 환경변수, 비밀 키 repr 제외, 공식 주소·후보 모델·제한 검사.
- contracts.py/client.py: 독립 미디어 계약, 요청 해시에 묶인 일회 승인, 종류별 생성1회, REST·상태 조회·다운로드·공식 사용량. POST 자동 재시도·유료 모델 전환 없음.
- providers.py/artifacts.py: 이미지/영상/TTS 구현체, 검증 후 로컬 MediaArtifact 반환. 실제 파일 ffprobe/전체 디코딩, raw PCM→WAV 변환.
- requests.py: 동일한 스타일·프롬프트 버전, 검증용 물의 순환 요청. API에 없는 파라미터를 임의 전송하지 않음.
- scripts/check_chatkhu.py: 오프라인 계획, 별도 preflight/live/resume. GET만 재개 가능.
- multimodal_schema.py: 기존 storyboard-1을 바꾸지 않는 media-plan-1. 명세 SHA256·scene_id, 로컬 자산 SHA256, 검토 상태, 렌더 모드, 외부 내레이션 원문 해시.
- services/multimodal.py: 기존 Gemini/mock 명세에 계획 연결. 시각 요청 제안은 네트워크 없는 승인 자료이며 이미지 검토 후 영상 승인을 별도로 요구.
- rendering/multimodal.py: 자산 복사·검증, 장면별 대체 사유, 검토된 크롭·이미지 줌·영상 반복, 외부 음성 피팅과 근사 자막.
- engine.py/worker.py/browser.py/assets: 선택적 미디어 입력. HTML/SVG 투명 레이어를 Playwright로 캡처하고 FFmpeg가 로컬 미디어와 합성. 기본 호출 계약·응답은 유지.
- render_storyboard.py: 선택적 --media-plan/--asset-root. compare_water_cycle.py: 승인된 로컬 결과만 재사용하는 A/B/C 비교.
- tests/test_chatkhu.py, tests/test_multimodal.py, tests/browser_multimodal.py 및 기존 회귀 스크립트.

## 공식 API 계약

KHU 개요에서 연결되는 공통 세부 문서와 브라우저 코드 예제를 확인했습니다. 아래는 사용한 최소 필드입니다.

| API | 확인한 요청·응답 |
| --- | --- |
| 인증 | 공식 HTTPS Gateway, Bearer 또는 x-api-key. 구현은 Bearer와 User-Agent |
| POST /images/generate/ | model/prompt/number_of_images/aspect_ratio. 동기 data[0].url 인라인 base64 또는 HTTPS; 비동기는 processing/operation_id와 GET 조회 |
| POST /video/generation/ | model/prompt/parameters/input_urls. operation_id → GET 상태 → completed/video_uri. 조회·다운로드에 원래 model 쿼리 |
| POST /audio/speech/ | model/input/voice. audio/pcm 24kHz/mono/signed16LE. X-Input-Tokens/X-Output-Tokens, 선택적 X-Billing |
| POST /estimate/ | image/video 견적의 credits/bound. TTS 견적 미지원 |
| GET /models/ | data 목록의 실제 모델 ID 확인 |

출처: [KHU 개요](https://docs.mindlogic.ai/docs/khu/api-gateway/getting-started/overview), [인증](https://docs.mindlogic.ai/docs/general/api-gateway/getting-started/authentication), [이미지](https://docs.mindlogic.ai/docs/general/api-gateway/reference/image-generation), [영상](https://docs.mindlogic.ai/docs/general/api-gateway/reference/video-generation), [TTS](https://docs.mindlogic.ai/docs/general/api-gateway/reference/audio-tts), [견적](https://docs.mindlogic.ai/docs/general/api-gateway/reference/estimate), [정산](https://docs.mindlogic.ai/docs/general/api-gateway/reference/pricing), [모델](https://docs.mindlogic.ai/docs/general/api-gateway/getting-started/models).

현재 모델은 gemini-3.1-flash-lite-image, fal-ai/kling-video/v3, gemini-3.1-flash-tts-preview입니다. 이미지 Lite의 image_size 허용값을 단정하지 않아 생략했습니다. Kling은3초/standard/generate_audio=false/9:16이며 확인하지 않은 resolution은 전송하지 않습니다. TTS instructions는3.8 전용이라3.1에 넣지 않았습니다. 대안 모델은 자동 호출하지 않습니다.

## 승인된 실제 호출과 공식 사용량

각 생성 전 예상 비용·호출 수를 알리고 별도 승인을 받았습니다. 이미지 minimum 견적과 TTS의 최종 비용 미확정도 알린 뒤 승인받았습니다. 추가 호출·재시도·모델 전환은 없습니다.

| 종류 | 실제 호출 | 실제 결과 | 시간 | 공식 응답 사용량 |
| --- | --- | --- | --- | --- |
| 이미지 | 생성 POST1, 동기 인라인 응답 | JPEG768×1376,576576bytes |3.611초 | credits_charged34.21 |
| 영상 | 생성 POST1, 상태 GET7, 파일 GET1 | H.264716×1284,24fps,73프레임,3.041667초,4659646bytes, 오디오 없음 |80.010초 | credits_charged252.0 |
| TTS | 생성 POST1 | PCM WAV24kHz/mono/s16le,19.4초,931244bytes |9.999초 | 입력76/출력485토큰. 차감액 미반환 |

사전 조회는 이미지 모델 GET1+무료 견적 POST1, 영상 모델 GET1+무료 견적 POST1, TTS 모델 GET1입니다. 이미지 사전 견적34/minimum은 상한이 아니고 실제 차감액도 아닙니다. 영상 견적252/exact는 생성 응답 보고액과 같았습니다. 시간은 접수·조회·다운로드·로컬 검증을 포함하며 순수 모델 추론 시간으로 표시하지 않습니다.

이미지·영상 공식 응답 보고액 부분 합계는286.21cr입니다. TTS X-Billing/credits_charged는 없으므로0으로 채우거나 토큰 단가 계산을 확정 비용으로 쓰지 않습니다. 조직 추가 콘텐츠 검사 비용 등 계정 전체 정산은 대시보드 확인이 필요합니다. 반복 폴링 금액은 합산하지 않으며 나중의 null 응답이 기존 공식 값을 지우지 않도록 테스트했습니다. 같은 자산을 재사용한 B/C 비용도 중복 청구처럼 합산하지 않습니다.

TTS 입력은129자의 물의 순환3문장, Aoede입니다. RMS -19.80dBFS, peak0.70108, clipped sample0을 확인했습니다. 실제 청취에 의한 발음·억양 평가는 수행하지 않았습니다.

## 원본 미디어 검토와 안전한 사용

이미지에는 제외 요청에도 흰색 화살표가 포함됐습니다. 물이 육지에서 산으로 거슬러 올라가는 것처럼 보일 수 있습니다. 영상은 구름 이동이 보이지만 중간·끝에 깨진 영문과 변형된 화살표가 생겼습니다. 증발·응결의 정확한 과정을 묘사했다고 인정하지 않았습니다. 파일 생성·재생은 성공했으나 원본의 학습용 직접 사용은 미통과입니다.

추가 유료 생성 대신 문제 영역을 제외했습니다. 물의 순환 자산은 requires_mask로 기록하고 상단30%와 하단20%만 사용합니다. 중앙은 합성에 입력하지 않습니다. 이미지 정지 화면과 영상73프레임의 크롭 연락판을 검사해 이 영역에 잘못된 라벨·화살표가 보이지 않는 것을 확인했습니다. 최종 화면은 하늘·태양·바다의 장식 배경과 정확한 SVG 과정도·한국어 자막을 조합합니다. 산과 대부분의 해안은 크롭에서 제외됩니다. 다른 자산에 이 크롭이 안전하다고 자동 판정하지 않습니다.

기록: tmp/chatkhu/image/visual-review.json, video/visual-review.json, video/frames/reviewed-crops-all-frames.png, tts/audio-review.json. 원본 파일과 공식 사용량은 각 디렉터리의 result.json/run-*.json에 있습니다.

## 장면 계획·시간·실패 정책

지원 모드: svg_animation, ai_image, ai_image_motion, ai_video, text_motion. 미디어 파일명은 안전한 basename, 자산 종류·확장자·SHA256·참조를 검증합니다. 명세나 narration이 바뀌면 기존 연결을 거절하거나 외부 음성을 대체합니다. 계획은 운영자가 승인하는 자료이며 LLM이 적은 검토 상태만으로 안전하다고 인정하면 안 됩니다.

function_graph/state_transition은 SVG를 강제합니다. 원본 미디어는 설명용 배경이며 수식·긴 글자는 SVG/기존 HTML이 표시합니다. ai_image_motion은 안전하게 크롭한 뒤 고정 타임라인으로 확대합니다. ai_video는 로컬 짧은 클립을 반복하고 원본 오디오는 무시합니다.

이미지·영상 누락/심볼릭 링크/해시 불일치/검토 거절/디코딩 실패/합성 오류는 장면별 SVG로 대체하고 사유를 보고합니다. 외부 음성의 텍스트 해시가 틀리거나 길이 피팅에 실패하면 macOS 음성으로 대체합니다. 과도한 발화는 최대1.35배만 조절하고 단어를 자르지 않습니다. 시간·디스크·취소 오류는 그대로 중단합니다. 유료 생성 실패 CLI는 원인을 알리고 멈추며 새 유료 요청을 보내지 않습니다. 미디어 없는 기존 로컬 렌더링은 계속 이용할 수 있습니다.

C의 음성19.4초를30초 타임라인에 무음 패딩합니다. 자막은 실제 음성 길이에 글자 수로 배분한 근사 정렬이며 음소·단어·문장 경계 검출을 주장하지 않습니다. 음성이 끝나면 복습 문장으로 전환합니다. 외부 TTS 문장이 실제 승인한 plan.json 원문과 같은지도 비교 스크립트에서 확인합니다.

## 실제 물의 순환 A/B/C 비교

같은 storyboard-1,3장면,30초 명세를 사용했습니다. 예제 명세는 deterministic mock이며 이 비교를 새 Gemini 호출 성공으로 세지 않습니다. 동일 서비스 함수는 기존 Gemini StoryboardSpec도 받을 수 있습니다. 새로운 API 호출 없이 승인된 파일을 장면 간 재사용했습니다.

| 결과 | 구성 | 프리뷰 합성 시간 | 기본 출력 합성 시간 | 관찰 |
| --- | --- | --- | --- | --- |
| A | SVG + macOS Yuna |8.406초 |55.156초 | 과정과 방향이 명확함. 장식 배경 없음 |
| B | AI 이미지 고정 크롭·확대 + SVG + Yuna |9.751초 |68.713초 | A와 같은 정확한 도식에 하늘·바다 배경 추가 |
| C | 이미지 + AI 영상 크롭·반복 + SVG + ChatKHU TTS |6.925초 |65.952초 | 구름 움직임·외부 음성 추가. 학습 과정 설명은 SVG가 담당하며 영상 루프는 장식적임 |

프리뷰는540×960/3fps, 기본 출력은1080×1920/30fps입니다. 모두 H.264/AAC48kHz mono,30.000초, YUV420P, 전체 디코딩 통과입니다. 두 조건의 A/B/C 모두 실제 오프라인 Chrome 탐색·재생을 통과했습니다. 기본 출력 C의2/9.5/18/25초 프레임을 검사해 자막 배치와19.4초 이후 복습 문장을 확인했습니다. 원본의 잘못된 라벨·화살표는 최종 크롭에서 보이지 않았습니다.

최종 파일: tmp/chatkhu/comparison/verified-full/A.mp4, B.mp4, C.mp4. 프리뷰는 verified-preview/. 명세·계획·comparison.json·*.render.json에 측정/대체/자산 재사용을 기록합니다. 합성 시간은 로컬 측정이며 API 생성 시간과 별개입니다. 보고서의 엔진·비용 메타데이터 정정은 재인코딩 없이 반영했고 report_metadata_revision=2로 표시했습니다. MP4 자체의 해시·검증 결과는 유지됩니다. 미적 품질·개념 전달력 관찰은 정성적이며 학습 효과를 측정한 결과가 아닙니다.

## 보안·자원 제한

- 실제 키는 backend 환경변수에서만 사용하고 worker 자식 환경에는 전달하지 않습니다. 일반 로그에는 원문 질문·자료·인증 정보를 남기지 않습니다.
- 요청25MB 미만, JSON32MiB, 다운로드100MiB, 입력 이미지8MiB. 생성 POST1/종류/클라이언트, 비동기 최대600초·60조회. CLI를 다시 실행해도 새 호출 승인이 자동 생기지 않습니다.
- 서명 외부 URL을 FFmpeg/브라우저에 전달하지 않습니다. 공식 Gateway 경로 또는 허용 fal.media HTTPS에서 인증을 분리해 로컬 복사합니다. 다른 호스트·리다이렉트는 차단합니다. URL 만료 기간과 원격 취소 API는 공식 문서에서 확인하지 못했습니다.
- 미디어 검증은4096px·16MP, 영상60초, 외부 PCM120초, 로컬 복사100MiB/파일·256MiB 합계. 기존512MiB 작업 예산·600초·단일 실행 잠금·worker/자식 종료·임시파일 정리를 재사용합니다.
- Playwright는 로컬 고정 코드와 검증 JSON만 실행합니다. 네트워크·서비스 워커·웹소켓을 차단하고 SVG/자막만 투명 PNG로 캡처합니다. FFmpeg는 고정 필터와 로컬 파일만 사용하며 shell=False입니다.
- 이 설계가 모든 악성 미디어 취약점을 막는 OS 격리나 모든 과학 내용의 자동 검증이라는 뜻은 아닙니다.

## 테스트와 실행

전체 pytest278개 통과: 기존206 + ChatKHU45 + 멀티모달27. 실제 API는 일반 테스트에서 호출하지 않습니다. 기존 FastAPI TestClient deprecation 경고1개는 유지됩니다.

실제 Chrome 검사: browser_rendering.py(6종 DSL 결정성·긴 한글·네트워크 차단), browser_multimodal.py(투명 레이어·SVG/텍스트·결정성·겹침), browser_rendered_videos.py(A/B/C 프리뷰·기본 출력), browser_smoke.py(원본 데모·HTML·모바일·fallback), browser_phase2.py(PDF·학습·오류), browser_phase3c.py(실제 웹 MP4·복구·Range·다운로드·소유권·대기/실행 취소·자식9개 정리)를 통과했습니다. 로컬 테스트 서버는 종료했습니다.

환경변수·명시적 호출·오프라인 합성 명령은 README의 Phase3-D 항목을 참고하세요. 실제 모델 추가 호출에는 새 승인이 필요합니다. 현재 남은 품질 확인은 한국어 발음·억양 청취 평가와 학습자/교사 검토이며 유료 재생성은 하지 않았습니다.
