# AHA! (아하!) · Phase 1

한국 고등학생을 위한 개념 학습 도우미의 로컬 PoC입니다. 기존 랜딩·수학·사회 데모를 유지하고, **자료 업로드 → 개념·질문 입력 → 학습 방식 선택 → 결과 학습**을 FastAPI에 연결했습니다.

현재는 **AI 생성이 아닌 수학 II 고정 예제**입니다. API 키, 유료 서비스, 외부 AI 호출 없이 실행합니다.

## 로컬 실행

Python 3.11 이상을 권장합니다. 이번 작업에서는 macOS / Python 3.13 / Chrome으로 검증했습니다.

프로젝트 루트에서:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

브라우저에서 **http://127.0.0.1:8765** 를 엽니다. 포트를 바꾸어도 프론트엔드는 같은 서버의 상대 경로로 연결됩니다. HTML 파일을 직접 여는 대신 FastAPI 주소로 접속하세요.

1. **내 자료로 시작하기**를 누릅니다.
2. PDF 또는 이미지 1개를 선택합니다. 자료 없이 질문만 입력해도 됩니다.
3. **예시 질문 채우기**를 누르거나 개념·질문 중 하나를 입력합니다.
4. **인터랙티브 학습 → 학습 결과 열기**를 누릅니다.
5. h를 조절하고 0.1, 0.01, 0.0001, −0.1, 0 버튼으로 기울기를 비교합니다.
6. **숏츠 학습**을 선택하면 기존 80.43초 가로형 예시 영상을 봅니다. 새 영상 생성은 하지 않습니다.

## 구현 범위

| 기능 | 현재 동작 |
| --- | --- |
| 자료 업로드 | PDF, PNG, JPEG, WebP 1개 / 최대 5 MiB. 확장자·MIME·파일 시작 서명 검사 |
| 개념·질문 | 개념 200자 / 질문 2,000자. 둘 중 하나 필수. 결과에 원문 표시 |
| 수학 결과 | 입력에 관계없이 f(x)=x², a=1인 로컬 템플릿 |
| 인터랙션 | 양수·음수 h, 할선·접선·두 점·변화량·기울기 차이 표시 |
| h=0 | 할선 기울기를 정의하지 않고 접선만 표시. 극한과 대입을 구분 |
| 숏츠 선택 | 원본 시안의 MP4 제공. 새 9:16 숏츠 생성 아님 |
| 오류 처리 | 파일·필드 검증, 중복 제출 방지, 로딩, 12초 타임아웃, 재시도 |
| 기본 예제 | API 오류·연결 실패 시 버튼으로 동일한 로컬 수학 템플릿 열기 |

PDF 텍스트 추출, OCR, 업로드 자료 기반 개인화, 외부 AI, TTS, 신규 MP4 렌더링·내보내기, 후속 질문, 저작권 자동 검토는 구현하지 않았습니다. 파일 서명 검사는 문서 전체의 유효성이나 안전성을 검증하는 기능이 아닙니다. 큰 발표용 PDF(약 32MB)는 업로드 제한에 걸리므로 실제 체험에는 5 MiB 이하의 교재 PDF나 필기 이미지를 사용하세요.

## API

`GET /api/health`

```json
{"status":"ok","mode":"local_demo","external_ai":false}
```

`POST /api/learn` — `multipart/form-data`

| 필드 | 값 |
| --- | --- |
| `file` | 선택, 파일 1개 |
| `concept` | 선택, 최대 200자 |
| `question` | 선택, 최대 2,000자. concept 또는 question 중 하나 필요 |
| `format` | 필수, `html` 또는 `shorts` |

```bash
curl http://127.0.0.1:8765/api/health
curl -X POST http://127.0.0.1:8765/api/learn \
  -F 'concept=미분계수의 기하학적 의미' \
  -F 'question=왜 할선의 기울기가 2에 가까워지나요?' \
  -F 'format=html'
```

응답에는 `mode`, `format`, 입력 원문, 파일 메타데이터, 자료 분석 상태와 가정, `lesson` 또는 `video`가 포함됩니다. `html`은 `/lessons/secant-tangent` 뷰어 주소, `shorts`는 기존 영상 주소를 반환합니다. 잘못된 입력은 422, 지원하지 않는 파일·요청 형식은 415, 크기 초과는 413입니다. multipart 파서 자체의 제한 위반은 400을 반환합니다. 파일 포함 전체 요청은 6 MiB로 제한합니다.

## 자료 처리와 실행 격리

- 자료와 질문을 외부 AI로 전송하지 않습니다. DB나 영구 업로드 폴더를 만들지 않습니다.
- 업로드는 요청 처리 중 메모리 또는 프레임워크 임시 파일을 사용할 수 있고, 처리 후 닫습니다. 파일 내용·질문 본문을 앱 로그에 기록하지 않습니다.
- 결과의 사용자 입력은 `textContent`로 표시합니다. 응답 HTML을 메인 DOM에 삽입하지 않습니다.
- 학습 결과는 `sandbox="allow-scripts"` iframe에서 실행합니다. `allow-same-origin`, 팝업, 폼 제출, 상위 화면 이동 권한을 주지 않습니다.
- 뷰어 응답에도 CSP sandbox를 적용하며, 고정 스크립트의 SHA-256 해시만 허용하고 네트워크 요청·외부 자산·폼·base URL을 막습니다. 뷰어 URL은 클라이언트에서 허용 목록으로 확인합니다.
- 모바일에서도 페이지 스크롤 하나로 읽도록 iframe 높이를 조절합니다. 높이 메시지는 해당 iframe에서 온 것인지 확인하고 300–2,200px 범위만 허용합니다.
- 현재는 검토 가능한 고정 템플릿만 실행하고 그래프를 유한 횟수로 그립니다. 임의 생성 코드의 CPU·메모리 실행 중단은 구현하지 않았습니다. iframe과 CSP만으로 완전한 보안을 보장하지 않으며, 이후 임의 코드 생성 전에는 별도 검증·실행 예산·격리 호스트 정책이 필요합니다.
- 로컬 PoC이므로 인증, 사용자별 저장소, 운영용 rate limit은 없습니다. 공개 서비스 배포 전 별도 구현이 필요합니다.

API 실패 시 기본 예제는 `/api/learn`을 거치지 않고 정적 템플릿을 엽니다. **서버 프로세스 전체가 중단되면 템플릿도 열 수 없습니다.** 외부 API는 현재 호출하지 않으므로 외부 API 장애에 의존하지 않습니다. 원본의 Google Fonts 링크는 유지했으며, 네트워크가 없으면 시스템 글꼴로 표시됩니다.

## 소스 구조와 수정 방법

```text
references/                    원본 HTML·기획 PDF (보존)
docs/                          제품 명세·구현 계획·검증 기록
backend/
  requirements.txt             서버 의존성
  app/main.py                  앱·정적 파일·뷰어 CSP·요청 크기 제한
  app/routes/learn.py           health·업로드·입력 검증
  app/services/lessons.py       고정 학습 응답
frontend/
  index.html                   원본에서 준비한 실행용 랜딩
  workflow.html                추가 학습 UI의 수정 원본
  static/workflow.css          기존 색상·글꼴 변수를 재사용하는 UI 스타일
  static/workflow.js           입력·API 연결·결과·오류·기본 예제
  static/media/                원본에서 그대로 추출한 MP4 2개
  lessons/secant-tangent.html  격리 실행할 고정 수학 템플릿
scripts/prepare_frontend.py    원본 + 추가 UI로 index·미디어 재구성
tests/test_api.py              API·입력 제한·원본 보존 검사
tests/browser_smoke.py         전체 흐름·기존 데모·브라우저 격리 검사
```

입력 화면을 바꿀 때 `frontend/workflow.html`을 수정한 후 다음 명령을 실행합니다. `frontend/index.html` 직접 수정은 재구성 시 덮어씁니다. 실행할 때마다 재구성할 필요는 없습니다.

```bash
python3 scripts/prepare_frontend.py
```

실행용 랜딩의 시각 요소·데모 스크립트는 유지했습니다. CTA를 학습 폼으로 연결하고, 현재 기능을 오해할 수 있는 자료 분석·맞춤 생성 문구에는 준비 중 상태를 표시했습니다. 원본의 통계·효과 주장은 이번 구현에서 별도로 검증하지 않았습니다.

## 테스트

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_api.py -q
node --check frontend/static/workflow.js
```

브라우저 검증은 위의 FastAPI 서버를 실행한 상태에서:

```bash
python tests/browser_smoke.py
```

macOS에 설치된 Chrome을 기본 사용합니다. 다른 환경에서는 `python -m playwright install chromium`으로 브라우저를 준비하거나 실행 파일을 지정하세요.

```bash
AHA_BASE_URL=http://127.0.0.1:8765 \
AHA_BROWSER_EXECUTABLE=/path/to/chrome \
python tests/browser_smoke.py
```

테스트 전용 환경 변수는 위 두 개뿐입니다. 앱 실행에 필요한 환경 변수나 비밀 키는 없습니다. 외부 AI·영상 API 설정은 아직 없으며, Elice 모델·인증·할당량의 실제 문서를 확인하는 Phase 2 이후 추가합니다. 비밀 키는 향후 환경 변수로 관리하고 저장소에 커밋하지 않습니다.

브라우저 스크린샷은 `tmp/screenshots/`에 생성됩니다. 검증 범위와 한계는 [Phase 1 기록](docs/PHASE1_NOTES.md)을 참조하세요.
# AHA-
