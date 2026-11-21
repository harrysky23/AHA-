# Claude 기반 범용 학습 숏츠

기존 main의 `3a86966`에서 FastAPI 비동기 숏츠 작업, PDF 분석, ChatKHU REST 클라이언트와 TTS Provider, React/Remotion 화면 및 FFmpeg 출력을 확인했다. 새 선택값 `AHA_VIDEO_RENDERER=claude`는 기존 HTML과 SVG/Remotion 경로 옆에 추가했다.

| 변경 파일 | 역할 |
| --- | --- |
| `backend/app/providers/chatkhu/client.py`, `settings.py`, `.env.example` | Bearer 인증 재사용, Claude 모델 설정, 모델·사용량·시간·오류 기록 |
| `backend/app/services/generated_video.py` | 자료 준비, 대본과 코드 파싱, 기존 TTS 호출, 파형 길이와 무음 구간을 바탕으로 시간 구성, 최대 1회 코드 수정, MP4 검증 |
| `backend/app/rendering/isolated.py`, `video-remotion/Dockerfile`, `.dockerignore`, `isolated/` | 실행 시간·자원 제한, Docker 프로세스 정리, 코드 검사와 격리 렌더링 |
| `video-remotion/src/VideoComposition.tsx`, `render.mjs` | 프로젝트 공통 React 화면에 생성 시각화만 삽입, 기존 Remotion 프레임 캡처 재사용 |
| `backend/app/video_config.py`, `routes/{learn,videos}.py`, `services/video_jobs.py`, `services/{storyboard_input,uploads}.py` | 기존 웹 작업의 선택 경로, 동의, 텍스트 자료, 상태·소유권·취소 |
| `frontend/workflow.html`, `frontend/index.html`, `frontend/static/{workflow,video-jobs}.js` | ChatKHU 안내, TXT 선택, 생성·수정 단계 표시 |
| `scripts/check_claude_video.py`, `tests/test_generated_video.py` | 단계별 실계정 검증 CLI와 네트워크 없는 회귀 검사 |

PDF는 기존 로컬 추출기, TXT는 UTF-8 검증을 사용한다. 이미지는 ChatKHU Claude Messages의 이미지 블록으로 전달한다. `claude-opus-5-5`가 목표·가정·대본·장면 계획·중앙 TSX를 반환한다. 한국어 문장들을 기존 TTS `gemini-3.1-flash-tts-preview`로 한 번 합성한다. 실제 WAV가 들어갈 만큼 타임라인을 잡고, 관측된 쉬는 시점과 문자 수로 장면·자막을 배정한다. 단어 수준의 정렬은 별도 검증이 필요하다.

컨테이너는 비루트 UID, 네트워크 없음, 읽기 전용 루트·입력, capability 제거, no-new-privileges, 3 CPU·2GiB 메모리·384 PID·700MiB 임시 공간으로 구동한다. TypeScript 구문과 타입, 허용된 JSX·AST·호출을 검사한다. TSX 실행은 컨테이너 Chromium에서만 이뤄진다. 더 강한 격리, 자동 과학 정확성 검증, 학생 공개 서비스는 이 PoC 범위 밖이다.

[모델 목록](https://docs.mindlogic.ai/docs/general/api-gateway/getting-started/models) · [ChatKHU Messages](https://docs.mindlogic.ai/docs/khu/api-gateway/reference/messages-api) · [TTS](https://docs.mindlogic.ai/docs/general/api-gateway/reference/audio-tts) · [크레딧과 환산](https://docs.mindlogic.ai/docs/general/api-gateway/reference/pricing)

## 검증 현황

- 계정 모델 목록 조회에서 `claude-opus-5-5`를 확인했다.
- 합성 TSX와 기존 WAV로 540×960·3fps, 1080×1920·30fps 30초 MP4를 실제 격리 렌더링했다. 실제 Claude의 코드 생성이나 내레이션·교육적 정확성 검증으로 집계하지 않는다.
- 최초 합성 렌더는 Chromium 프로세스 한도에 막혔다. 한도를 조정하고 새 헤드리스 모드로 변경한 후 완료했다. 이후 렌더에서 이미지/영상 생성 API 호출은 0회다.
- 2026-11-22 A 미분계수 첫 호출은 Chat Completions에서 입력 764·출력 5,500토큰, 모델 응답 48.482초였다. 출력 한도에 도달한 뒤 완성 코드를 확보하지 못해 수정·TTS·렌더가 시작되지 않았다. 같은 날짜 해당 키의 모델별 Gateway 사용량은 1건, 113.73크레딧이었고 잔액은 3,574.43크레딧이었다.
- 두 번째 시도에는 같은 키와 모델로 ChatKHU Messages의 `output_config.effort=low`를 지정했다. 출력 한도는 5,500으로 유지하고 TSX 분량을 줄였다. Messages 응답에서는 텍스트 블록과 종료 사유를 각각 검사한다. [Opus 5.5 추론과 출력 예산](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide) · [Gateway 사용량 조회](https://docs.mindlogic.ai/docs/general/api-gateway/reference/usage)
- B 수요·공급과 C 전자기 유도의 유료 검증은 별도 승인 범위다.

### 미분계수 실계정 결과

`tmp/claude-video/A/video.mp4`를 생성했다. 1080×1920, 30fps, 30초 H.264/AAC이고 전체 디코딩과 Chrome 탐색·재생을 통과했다. 이미지 생성·영상 생성 API 호출은 모두 0회다.

| 작업 | 모델 | 입력 토큰 | 출력 토큰 | 소요 시간 |
| --- | --- | ---: | ---: | ---: |
| 첫 생성 | `claude-opus-5-5` | 764 | 5,500 | 48.482초 |
| Messages 생성 | `claude-opus-5-5` | 804 | 2,520 | 21.557초 |
| 자동 코드 수정 1회 | `claude-opus-5-5` | 2,958 | 1,989 | 15.698초 |
| 승인된 TTS 재개 | `gemini-3.1-flash-tts-preview` | 100 | 628 | 9.941초 |
| 최종 Docker 렌더 | 로컬 Remotion·FFmpeg | — | — | 57.976초 |

Gateway의 2026-11-22 키·모델별 사용량은 Claude 3회 218.96크레딧, TTS 1회 12.66크레딧이었다. 두 번의 코드 생성 시도와 수정 1회, 마지막 TTS의 합계는 231.62크레딧이며 조회 시점 잔액은 3,456.54다. 둘째 생성과 수정의 합계 차감액은 이전 Claude 사용량을 뺀 105.23크레딧이다. Gateway 사용량 조회가 모델별 합계만 제공하므로 생성과 수정의 개별 차감액은 분리하지 않았다.

자동 생성·수정은 검증기가 `ConditionalExpression`을 허용하면서 그 안의 `QuestionToken`과 `ColonToken`을 허용하지 않아 모두 거절됐다. 검증기에 두 토큰을 추가하고, 보관된 두 번째 Claude 코드의 JSX 속성 펼치기를 명시적인 SVG 좌표로 바꿨다. 내레이션에는 할선 기울기 공식에 필요한 `h≠0` 조건을 보완했다. 로컬 WAV로 프리뷰를 검증한 뒤 `--resume-draft`로 Claude 재호출 없이 남은 TTS 1회와 최종 렌더를 진행했다. 최종 재개는 총 69.479초였다. 이 결과는 사람이 초안을 검토·보정한 결과이며 자동 경로 전체는 아직 검증되지 않았다.

대본의 기준점은 P(1,1)이다. 검토한 프레임에서 Q는 곡선 위에서 P로 접근하고, 할선의 기울기 `2+h`가 2에 가까워지며 마지막에 접선 `y=2x−1`과 `f′(1)=2`가 표시된다. 한국어 글자가 표시되며, 25.12초 음성의 쉼을 기준으로 약 6.04·11.84·18.53초에 장면을 전환한다. 단어별 음성 정렬은 측정하지 않았다.

세 작업의 `report.json`과 저장된 원본·수정 TSX는 `tmp/claude-video/A/`의 작업별 디렉터리에 있다. 최종 프레임은 같은 디렉터리의 `frame-*.png`에 보관한다. 이전 결과는 제3의 모델로 대체하지 않았다.
