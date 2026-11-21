# Storyboard DSL · storyboard-1

Phase 3-A의 출력은 검토할 스토리보드 JSON입니다. 이 문서는 향후 HTML/SVG → Playwright → FFmpeg 렌더러가 따라야 할 **입력 계약**이며, 현재 렌더러·TTS·영상 파일 저장은 구현하지 않았습니다.

Pydantic 원본은 `backend/app/storyboard_schema.py`입니다. Phase 2 `LessonSpec(schema_version=1)`과 별개입니다. 임의 함수식·코드·명령·URL·파일 경로·SVG path·스타일 사전을 받는 필드는 없습니다.

## 공통 형식

- `schema_version`: `storyboard-1`.
- `topic`, `learning_objectives`, `student_level`, `difficult_point`: 주제·목표·설명 수준·질문의 어려운 점. 수준은 foundation/high_school/advanced이며 성취도 진단이 아닙니다.
- `duration_seconds`: 정수 30–60초. 요청의 목표 길이와 같아야 합니다.
- `video`: aspect_ratio=9:16, width=1080, height=1920, fps=30.
- `scenes`: 3–8개, ID 고유. 각 장면 2초 이상. 0초부터 정렬·연속 배치하며 겹침·공백 없이 마지막 종료가 총 길이와 같아야 합니다.
- `start_seconds`, `end_seconds`: 전체 영상 기준 시간. 0.1초 단위. 장면 구간은 `[start,end)`이며 마지막 끝은 영상 끝입니다.
- `screen`: title(최대80자), bullets(최대3개, 각각280자), formulas(최대3개, 각각80자). 모두 평문입니다. 수식도 프로그램이나 TeX 명령으로 실행하지 않습니다.
- `narration_ko`: 한국어가 포함된 10–500자 텍스트. 시간 배치·길이 상한을 확인하지만 실제 발화 시간이 장면에 맞는지는 TTS 구현 후 검증해야 합니다.
- `source_ids`: 전체 sources의 ID 참조. 없는 ID·중복 ID는 거절합니다.
- `cues`: 최대12개. 장면 내부 상대 시간 `at_seconds`, `action=reveal|highlight|hide`, `target_id`. 시간순·장면 길이 안·존재하는 요소만 허용합니다. `text_explanation`은 요소 ID가 없어 cues=[]입니다.
- `material_usage`: used/not_relevant/unavailable. 사용한 자료는 실제 인용이 있어야 하며 모든 인용은 최소 한 장면에서 참조해야 합니다.
- `sources`: 최대3개. id, page(1–20), quote(최대240자). 제공한 PDF 추출 텍스트와 페이지·인용 문자열을 비교합니다. 공백 차이만 정규화합니다.
- `assumptions`: 1–5개. 설명용 수치·단순화·자료 부족을 밝힙니다.
- `review_status`: ready_for_review/needs_context. 검토 가능 상태를 사실성 검증 완료로 해석하지 않습니다. needs_context이면 limitations가 필수입니다.

모든 객체는 추가 필드를 금지합니다. 수치는 유한해야 하며 bool·문자열을 숫자로 자동 변환하지 않습니다. ID는 영문 소문자로 시작하는 최대32자 식별자입니다. 장면 내부 시각 요소 ID도 고유해야 합니다.

## 6종 시각화

각 장면의 `visualization.type`이 아래 데이터 형태를 결정하는 discriminated union입니다.

| 유형 | 허용 파라미터·상한 | 검증 |
| --- | --- | --- |
| function_graph | x/y label·range, curves 1–4, markers 최대8, connectors 최대4, marker_keyframes 최대16 | 축 min<max, 뷰포트 안 마커, 고유 ID·연결·곡선 참조, 키프레임 순서·좌표 |
| process_diagram | flow=sequence/cycle/network, nodes 2–8, edges 1–12 | 노드·간선 ID, 유효한 두 노드 연결, cycle의 첫 노드로 돌아오는 순환 |
| timeline | time_unit=year/second/step, events 2–8 | 각 event의 position이 엄격히 증가, ID 고유 |
| comparison | left_title, right_title, rows 1–5 | 각 row의 id·aspect·left·right·emphasis(none/left/right) |
| state_transition | states 2–8, transitions 1–12, initial_state, steps 1–10 | t=0의 초기 상태부터 시작, 선언된 전이만 사용, 시간 증가·상태 참조·배열 인덱스 |
| text_explanation | heading, paragraphs 1–3, fallback_reason | 대체 이유 필수, 각 문단 최대280자 |

함수 그래프의 숫자 좌표·다항식 계수는 −1000부터1000, 최대3차입니다. timeline.position은 −10000부터10000입니다. 연도의 사실성을 범위 검사로 보장하지 않습니다. 정확한 연대의 근거가 없으면 순서 단위(step)나 텍스트로 대체하도록 프롬프트에 명시했습니다.

## 렌더러 계약

다음 규칙은 이후 구현 시 사용할 해석 방법입니다. Phase 3-A에서 프레임·화면·MP4를 만들지는 않습니다.

### 고정 영역과 텍스트

1080×1920 캔버스에서 제목·시각화·자막 영역을 고정 템플릿으로 분리합니다. 권장 안전 영역은 제목 `[72,100,936,180]`, 시각화 `[72,340,936,1120]`, 내레이션 자막 `[72,1540,936,260]` (x,y,width,height)입니다. 모델은 이 좌표를 바꾸지 않습니다.

과정·상태 노드의 x,y는 **시각화 영역에 대한 정규화 좌표**(.05–.95)이며 중심점입니다. 화면 문구·수식·인용·노드 라벨은 반드시 이스케이프한 텍스트로 배치합니다. 줄바꿈·폰트 크기·실제 텍스트 넘침 검사는 미래 렌더러 책임입니다. 콘텐츠 길이 제한만으로 완벽한 레이아웃을 보장하지 않습니다.

palette는 violet/yellow/pink/blue/green만 허용하고 실제 색상·선·노드 스타일은 소유한 템플릿에서 고정합니다. 예: violet=#7b5cf0, yellow=#ffd23f, pink=#ff6b9a, blue=#3b82f6, green=#16a34a. 생성된 CSS를 실행하지 않습니다.

### 함수·마커·연결선

`coefficients=[c0,c1,c2,c3]`는 `c0+c1*x+c2*x²+c3*x³`입니다. 빠진 높은 차수는0이며 계수는 최소1개입니다. 문자열 파싱·eval 없이 고정 다항식 계산 코드로만 평가합니다. 곡선마다 최대240개 구간을 사용하고 그래프 영역에서 clip합니다.

`markers`는 id,label,point,color,선택적 curve_id를 갖습니다. curve_id가 있으면 초기 위치와 모든 키프레임의 y를 해당 다항식과 비교합니다. 키프레임은 마커별 t=0 이후 엄격히 증가하며 장면 길이를 넘을 수 없습니다.

렌더러는 기본 마커 위치를 t=0 값으로 사용하고 키프레임 사이를 선형 보간한 뒤 마지막 값을 유지합니다. **curve_id가 있는 마커는 x만 보간하고 y를 다항식에서 다시 계산**합니다. x,y를 각각 직선 보간해 움직이는 점이 곡선 밖으로 나가게 만들면 안 됩니다.

`connectors`는 start_marker/end_marker의 현재 위치를 잇습니다. extend=true는 그래프 영역 경계까지 연장하고 clip합니다. 수직선은 별도로 처리하며, 두 마커의 위치가 같아지면 해당 선을 숨기거나 점으로 처리해야 합니다. 0으로 나누거나 정의되지 않은 할선 기울기를 계산하지 않습니다.

### 과정·타임라인·비교

과정도는 명시적 노드 좌표와 방향 간선을 사용합니다. 라벨을 명령이나 프로그램으로 해석하지 않습니다. timeline은 position의 범위를 세로 축에 매핑하고 time_label은 그대로 표시합니다. time_unit=step의 1,2,3은 순서이며 역사 연도가 아닙니다. 비교는 rows의 공통 aspect를 기준으로 두 열을 나란히 표시합니다.

### 상태·자료 흐름

state의 items는 최대16개 **표시용 문자열**입니다. 계산 코드가 아닙니다. highlight_indices는0부터 시작하며 배열 범위 안의 고유 인덱스입니다. 선택적 active_range(low/high)는 양 끝 포함 구간이며 highlight도 그 안에 있어야 합니다. 이진 탐색 예제에서는 제외 구간을 흐리게 표시하는 데 사용할 수 있습니다.

현재 상태는 steps에서 해당 상대 시간 이하의 마지막 state_id를 선택하는 계단 함수로 결정합니다. 중간 상태를 추측하거나 생성하지 않습니다. 시작은 t=0의 initial_state, 이후 다른 상태로 이동할 때는 선언된 transition이 존재해야 합니다. caption을 실행하지 않습니다.

### cues와 프레임 시간

cues는 나열된 순서대로 해당 상대 시점부터 적용합니다. 같은 시점의 충돌은 배열의 마지막 항목이 우선합니다. reveal/hide는 요소 가시성, highlight는 고정 템플릿의 강조 상태만 바꿉니다. 처음부터 보일 요소는 기본 visible이며 reveal 전에 숨길 요소는 t=0 hide를 명시합니다.

모든 상대 시간은 scene.start_seconds를 더해 전체 영상 시간으로 변환합니다. 0.1초는30fps에서3프레임이므로 프레임 인덱스를 정수로 계산할 수 있습니다. 장면 사이 기본 전환은 hard cut입니다. crossfade·임의 카메라·외부 미디어·실행 코드는 이 DSL에 없습니다.

## 검증 범위와 한계

명세 형태·타이밍·참조·알려진 곡선 좌표·원문 인용 일치를 확인합니다. 과학·역사·사회 전체 사실성, 인용 의미·관련성, 설명 난이도, 레이아웃, 실제 음성 길이는 완전 검증하지 않습니다. 부족한 맥락은 limitations와 text_explanation으로 처리합니다.

명백한 코드·마크업 패턴도 거절하지만 문자열 금지 목록 자체를 보안 경계로 삼지 않습니다. 근본 원칙은 타입별 고정 데이터만 해석하고 어떤 문자열도 프로그램으로 실행하지 않는 것입니다. 미래 렌더러는 검증을 다시 적용하고 이스케이프·격리·자원 제한을 유지해야 합니다.
