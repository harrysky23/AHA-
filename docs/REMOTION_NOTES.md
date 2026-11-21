# Remotion 도입 · 물의 순환 모션그래픽

## 분석과 설계

2026-11-21, main에서 기존 Phase3-A/B/C/D 코드를 확인했습니다. Phase3-D 변경은 이미 스테이징되어 있었고, 해당 상태를 해제하거나 커밋하지 않고 추가 변경을 작업했습니다. AGENTS·제품 명세·구현 계획·기존 렌더러·TTS·작업 큐를 읽었습니다. 원본 references HTML은 다시 만들지 않았습니다.

기존 구조는 학생 자료/질문 → PDF 분석 → Gemini 또는 mock StoryboardSpec → 별도 worker의 로컬 TTS/HTML·SVG·Playwright → FFmpeg → ffprobe/전체 디코딩 → 비동기 웹 작업의 보호된 MP4 공개입니다. Phase3-D는 별도의 MediaPlan과 검토된 로컬 이미지·영상·음성으로 합성합니다. 원본 C.mp4는30초1080×1920/30fps였고 중앙은 순환 다이어그램에 가까웠습니다.

이번에는 FFmpeg 경로를 유지하고 **React/TypeScript + Remotion**을 추가했습니다. Remotion이 영상 모델을 호출하지 않으며, 검증된 장면 데이터를 프레임에 따라 그립니다. 최종 음성 합성·MP4 인코딩·검사는 기존 FFmpeg 도구를 재사용합니다. AI Provider와 LessonSpec/StoryboardSpec 응답은 변경하지 않았습니다.

## 변경 파일

| 파일 | 역할 |
| --- | --- |
| video-remotion/package.json, package-lock.json, tsconfig.json | 별도 고정 버전 React/TypeScript/Remotion 환경 |
| src/VideoComposition.tsx | VideoComposition·SceneRenderer·BackgroundLayer·NarrationText·SubtitleLayer·AudioTrack·TransitionLayer·BrandOverlay |
| src/ConceptAnimation.tsx, motion.mjs, types.ts | 검증된 물의 순환 SVG·경로·입자·타입. 타이머/Math.random/CSS 시간 애니메이션 없음 |
| examples/water-cycle-cues.json | 기존 WAV에 맞춘6장면·8자막 큐, 원본 음성 SHA256 |
| render.mjs | 공식 bundle/selectComposition/renderFrames/renderStill, CDP 요청 제한, 프레임/레이아웃 감사 |
| studio.mjs | 느낌표 경로를 위한 로컬 Studio 래퍼 |
| backend/app/remotion_schema.py | remotion-plan-1, 시간·자막 원문·명세/음성 해시 검사 |
| rendering/remotion.py | 기존 TTS·검토 이미지 준비, Remotion 프레임 → FFmpeg 인코딩 → 기존 MP4 검사 |
| rendering/engine.py, worker.py | 선택적 Remotion 경로, 기존 자원/취소/정리 경계 재사용 |
| rendering/multimodal.py | Remotion이 원본 음성을 재사용할 때 불필요한 atempo=1 필터를 생략하는 선택 옵션. 기존 기본값 유지 |
| video_config.py, services/video_jobs.py | AHA_VIDEO_RENDERER=svg/remotion, 기존 비동기 작업 API/소유권/상태 유지 |
| scripts/render_storyboard.py, render_remotion.py | 일반 명세 및 기존 C 예제의 로컬 자동 렌더링·Studio 준비 |
| tests/test_remotion.py, video-remotion/tests/motion.test.mjs | 스키마·안전·선택·궤적·결정성 검사 |
| tests/check_remotion_output.py | 기존 출력의 음성 파형·자산 보존·프레임 감사·비교 페이지 |

기존 Gemini/ChatKHU Provider, 자료 추출, 웹 폼, HTML 학습, 원본 데모, 기존 SVG 컴포넌트를 유지했습니다. .env 값은 수정·출력하지 않았습니다. 새 설정은 .env.example에만 추가했습니다.

## 장면과 음성 재사용

기존 tmp/chatkhu/comparison/verified-full의 StoryboardSpec, 검토 이미지,19.4초24kHz/mono WAV를 사용합니다. 이미지·음성의 해시를 검사하고 이미지의 잘못된 화살표/AI 라벨 영역은 기존 상단30%·하단20% 크롭으로 제외합니다. Remotion 중앙 지형·구름·강·텍스트는 프로젝트가 소유한 SVG/React 코드입니다. 기존 AI 영상은 새 장면에 사용하지 않고 비교 원본 C에 보존합니다.

| 구간 | 영상 시점 | 설명과 움직임 |
| --- | --- | --- |
| 도입 |0–1.25초 | 물의 순환 제목·배경 등장 |
| 증발 |1.25–7.25초 | 바다에서 수증기 모형 입자가 상승 |
| 응결 |7.25–13.8초 | 입자가 모이고 구름이 점진적으로 형성 |
| 강수 |13.8–16.5초 | 구름에서 지표로 빗방울 하강 |
| 유출·집수 |16.5–20.4초 | 하천 경로를 따라 바다로 이동 |
| 정리 |20.4–30초 | 전체 순환과 복습 문장 |

원본 WAV를1초 늦게 시작하고 변속 없이 재사용합니다.19.4초 전체가 들어가며 끝에는 무음을 채웁니다. 자막은 원본의 절을 그대로 사용하고 중요 용어를 강조합니다. 무음 구간을 참고해 조정한 타임스탬프이며 ASR/음소 강제 정렬이나 실제 청취 검증으로 주장하지 않습니다. 원본에서 없는 내레이션은 추가하지 않았습니다.

유출 궤적은 화면 좌표에서 아래쪽으로 단조롭게 이동하도록 검증했습니다. 수증기는 보이지 않는 기체이며 점은 이동을 나타낸 모형이라고 표시합니다. 증산·지하수 저장 등은 생략한 설명 모형이며 모든 자연 현상을 시뮬레이션했다고 주장하지 않습니다. 프레임 기반 fade/이동/spring/스케일을 사용하며 큰 효과보다 설명 단계의 입자 움직임을 우선했습니다.

일반 웹 생성에서는 기존 MacOSSay가 만든 장면별 실제 길이를 이용하고 긴 문장은 나누어 표시합니다. 외부 전체 음성에 명시적 큐가 없으면 글자 수 기반 근사임을 estimated_character_time으로 기록합니다. 다른 개념은 기본 텍스트 템플릿으로 대체합니다. Remotion에서 모든 기존 DSL을 구현했다고 표시하지 않으며 기존6종은 SVG 렌더러에서 계속 사용할 수 있습니다.

## 백엔드·보안·자원 경계

- 기본 renderer는 svg. AHA_VIDEO_RENDERER=remotion으로 서버를 재시작하면 기존 POST/GET/DELETE /api/videos와 보호된 Range 파일 제공을 사용합니다. HTTP 요청에서 렌더링 완료를 기다리지 않습니다.
- 같은 ThreadPoolExecutor/별도 Python worker/단일 실행 flock/ProcessTree/watch_parent/시간·용량 제한/취소 승인 후 정리를 재사용합니다. Node/Chrome/esbuild/FFmpeg도 worker 자식으로 추적합니다.
- RemotionPlan은 명세·원문·음성 해시에 묶이며 장면 연속성, 겹침·길이, 자막 원문과 시간, 허용된 타입과 필드만 받습니다. 미지원 타입은 text_explanation입니다.
- 렌더 페이지는 로컬 번들만 실행합니다. 외부 HTTP(S), 웹소켓·서비스워커를 차단하며 자산 참조는 generated/ 아래 고정 로컬 파일명만 허용합니다. 임의 JS/Python/HTML을 데이터에서 실행하지 않습니다. CSP·CDP는 OS 전체 네트워크 격리라고 주장하지 않습니다.
- worker는 API 키를 상속하지 않고 번들에 환경변수를 주입하지 않습니다. 오류/진행 로그는 원본 질문·자료·명세·인증 헤더를 출력하지 않습니다.
- AHA!의 !는 Webpack 로더 예약 문자와 충돌했습니다. 부모가 예약 문자 없는 임시 별칭을 만들고 Node/모듈/webpack에 lexical 경로를 유지합니다. 실제 결과·브라우저 프로필·임시 파일은 원래 작업 폴더에 두어 예산 검사에 포함하고 자식 종료 후 별칭도 제거합니다.
- 일반 렌더에 감사 코드를 강제하지 않습니다. --audit는 의도적으로 차단할 테스트 URL을 요청하고 PNG 결정성·입자 좌표를 기록합니다. 이 요청은 CDP에서 차단됐으며 유료 API 호출이 아닙니다.
- Studio는 개발용 별도 서버입니다. 고정 합성 예제만 public/generated로 준비했고 API 키는 전달하지 않았습니다. Studio에서 생성 --props 파일이 기본값보다 우선하며 원본 큐/JSON으로 내용을 수정할 수 있습니다.

## 실제 결과와 비교

최종본: tmp/remotion/release/water-cycle.mp4. 원본은 tmp/chatkhu/comparison/verified-full/C.mp4와 release/C-original.mp4로 모두 보존했습니다. release/comparison.html은 두 플레이어를 나란히 표시합니다.

| 항목 | 기존 C | Remotion 최종본 |
| --- | --- | --- |
| 출력 |1080×1920,30fps,30초,H.264/AAC | 동일,900프레임,YUV420P,AAC48kHz mono |
| 중앙 | 과정 노드·연결선 위주 | 지형과 증발·구름·빗방울·하천 입자의 단계별 움직임 |
| 자막 | 전체 음성 길이에 글자 수로 배분 | 실제 무음 구간 참고·편집 가능한 절 큐, 핵심 용어 강조 |
| 배경 | 검토된 AI 이미지/영상 크롭 | 같은 이미지 크롭·느린 확대 + 직접 그린 SVG |
| 음성 | 기존 ChatKHU WAV | 같은 WAV,1초 시작 지연,변속 없음 |
| 로컬 생성 시간 | Phase3-D 기록65.952초 |54.063초(프레임 감사 포함) |
| 파일 크기 |2,876,971bytes |3,380,098bytes |
| 새로운 외부 AI 호출 | 이번 비교0 |0 |

시간은 이 장비의 단일 실행 관찰이며 일반적인 성능 우위·학습 효과를 측정한 결과가 아닙니다. 새 유료 영상/TTS API·Gemini 생성은 호출하지 않았습니다.

최종본 ffprobe/전체 디코딩과 실제 오프라인 Chrome 탐색·재생을 통과했습니다. 원본 음성19.4초의 모든 샘플 구간이 지정된1초 지연 이후 포함됐고, AAC 디코딩 후 원본과 파형 상관계수0.999682였습니다. 이는 손실 압축·리샘플링을 허용한 음성 보존 검사이며 자막의 음소 정렬이나 발음/억양 청취 평가가 아닙니다.

75/135/270/450/555프레임으로 각 단계 입자를 검사했습니다.75프레임을 재렌더한 PNG SHA256이 같았고 다른 시점의 입자 좌표는 달랐습니다. 증발/응결/강수/유출 입자4종, 한국어 배치와 안전 영역24건을 확인했습니다. 최종 감사의 외부 요청9건은 의도한 테스트 요청이며 모두 차단됐습니다. 평상시 웹 렌더링에는 이 테스트 요청이 없습니다. 추출한2.5/4.5/8/10/14.5/15.5/18/19/25초 프레임을 보존합니다.

원본 C SHA256:229323930d997a87bb70d1be54c26edea5adc2b6bb9da6b91a0260aa42e4a1aa.
Remotion SHA256:0650a75e8733d2053155035805fb3a0bbc2ada5a19a13eb5d16de680872e61b5.

## 검증 목록

- Python 전체294개 통과(기존278 + Remotion15 + 음성 보존1). 기존 FastAPI TestClient deprecation 경고1개 유지.
- TypeScript noEmit 검사 통과. Node 궤적/결정성/로컬 참조/장면 경계4개 통과.
- --audit 프리뷰와 최종 기본 출력 생성·프레임 검증 통과. tests/check_remotion_output.py로 재검사 가능.
- Remotion Studio 실제 실행·브라우저 표시를 확인했습니다. 프리뷰 props의3fps가 표시됐고 한국어·배경·음성 자산이 로드됐습니다. 기본 prepare-studio 명령은30fps입니다.
- mock AI + Remotion 서버에서 browser_phase3c.py 통과: PDF → 명세 → 실제 MP4 → 새로고침 복구 → 모바일 재생/Range/다운로드/접근 제어 → HTML, 대기/실행 취소. Node/Chrome을 포함한 자식11개 종료 확인.
- Remotion 실행 중 SVG 요청은 render_busy로 거절돼 공유 잠금을 존중했습니다. 완료 후 기존 --renderer svg로 실제30초540×960 MP4 생성/디코딩 통과.
- 다른 개념의 Remotion 텍스트 대체도 별도 mock 프리뷰로 검사합니다. 기존 HTML/Provider 테스트와 원본 C/참조 HTML을 유지했습니다.
- 테스트 API/Studio 서버는 종료했습니다. 잔여 렌더 별칭0개를 확인했습니다. 변경은 커밋/푸시하지 않았습니다.

## 설치 버전과 라이선스

실제 npm 조회에서 Remotion 최신 배포는4.0.545였으며 @remotion/bundler/cli/renderer/remotion을 같은 버전으로 고정했습니다. React19.2.4, TypeScript5.9.3, Node26.5.1 환경에서 검증했습니다. 설치·로컬 실행 명령과 서버 설정은 README에 있습니다. node_modules·생성 자산·결과물은 Git에서 제외하고 package-lock.json을 보존합니다.

설치된 Remotion LICENSE와 [공식 원문](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)에 따라 개인,3인 이하 영리 조직,비영리 조직,비상업적 도입 평가 등에 무료 자격이 있고 그 밖의 경우 Company License가 필요합니다. 이번 구현은 로컬 도입 평가이며 실제 조직의 상업 운영 자격을 확정하지 않았습니다. 라이선스를 구매하거나 과금 사용량을 등록하지 않았습니다. MIT로 표기하거나 모든 팀에 무료라고 보장하지 않습니다.

구현 근거: [renderFrames](https://www.remotion.dev/docs/renderer/render-frames), [openBrowser](https://www.remotion.dev/docs/renderer/open-browser), [서버 렌더링](https://www.remotion.dev/docs/renderer/render-media), [Html5Audio](https://www.remotion.dev/docs/html5-audio). 네트워크 차단에 사용한 Remotion Page의 CDP 접근은 고정 설치 버전의 타입·구현을 확인했으며 버전 업그레이드 때 감사 테스트를 다시 실행해야 합니다.
