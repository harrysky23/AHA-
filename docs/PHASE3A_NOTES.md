# Phase 3-A · 스토리보드 구현 기록

2026-11-21. 작업 시작 기준 main은 `6cd654d`이며 작업 폴더는 깨끗했습니다.

## 구현 범위

- 별도 `StoryboardSpec(schema_version=storyboard-1)`과 6종 선언형 시각화 DSL.
- 30–60초·9:16·1080×1920·30fps, 장면 시간·화면 문구·수식·한국어 내레이션·학습 목표·수준·어려운 점·자료 인용·가정.
- mock/Gemini/Elice Provider의 `generate_storyboard` 경로.
- `POST /api/storyboard` multipart API, 기존 PDF 처리·업로드 제한·전송 확인 재사용.
- 전용 프롬프트 `storyboard-ko-v1`, 별도 스키마·토큰 예산·캐시 namespace.
- 기본 mock CLI와 명시적 `--live` 검증 스크립트.

렌더러가 따라야 할 해석은 [DSL 계약](STORYBOARD_DSL.md)에 정리했습니다. 이번 구현은 JSON만 반환하며 **MP4·TTS·FFmpeg·Manim·영상 저장은 구현하거나 실행하지 않았습니다.** 프론트엔드는 수정하지 않았고 기존 shorts 선택은 계속 기존 예시 영상을 제공합니다.

## 기존 코드 재사용

| 기존 부분 | 변경 방식 |
| --- | --- |
| providers/ | 기존 generate 유지, generate_storyboard를 별도 추가 |
| Gemini REST | generate_json·response_text로 HTTP/오류/응답 추출을 공유. HTML parse_spec과 storyboard parser는 분리 |
| response_schema | 기존 nullable 변환 유지, 새 discriminated union의 서로 다른 literal 태그를 anyOf로 변환 |
| materials.py | 그대로 재사용. 새 API의 자료 없음 안내만 범용 문구로 변경 |
| cache.py | TTL/LRU·동시 중복 공유 구현 재사용. 반환값 타입 일반화·HMAC fingerprint 추가 |
| uploads.py | 기존 파일 검증만 추출. 기존 learn 모듈의 상수·함수 import 호환 유지 |
| /api/learn | 기존 입력·응답 구조·HTML·기존 영상 동작 유지 |

새 코드: storyboard_schema.py, routes/storyboard.py, services/storyboard*.py, services/uploads.py, scripts/check_storyboard.py, tests/test_storyboard.py.

## 검증

`python -m pytest -q`: **155개 통과**. 기존 Phase 1·2의80개와 새75개를 포함합니다. TestClient의 기존 httpx deprecation 경고1개는 남아 있습니다.

- 4개 요청 개념 × 30/45/60초 API 결과.
- 미분계수 → function_graph·comparison, 물의 순환 → process_diagram, 수요/공급 → function_graph·comparison, 이진 탐색 → state_transition. 마무리는 text_explanation.
- timeline을 포함한 6종 타입 각각의 양성 검증과 임의 코드·명령·HTML·SVG·경로·URL 추가 필드 거절.
- 장면 겹침·공백·순서·2초 미만·전체 길이 초과·끝 미일치·가로 규격·한국어 없는 내레이션·코드 펜스 거절.
- 잘못된 축·곡선 식 문자열·마커 좌표·곡선 참조·연결선·키프레임, 잘못된 노드·순환, 타임라인 정렬, 비교 ID, 상태·배열·범위·전이 검증.
- PDF 추출·인용·위조 인용·무관 자료 표시·텍스트 없는/손상 PDF 안내.
- 독립된 스토리보드 캐시, 길이·수준·예산·프롬프트 변경에 따른 키 변경, 실패 명세 미저장.
- Gemini HTTP 대역으로 전용 JSON Schema·질문·수준·길이 전달, 자료의 지시를 user 데이터에만 포함, 429·전송 확인·키·원문 비노출.
- Elice와 mock이 HTTP 클라이언트를 생성하지 않음.
- 기존 /api/learn HTML·기존 영상과 응답 구조 유지.

`python scripts/check_storyboard.py --all`: 실제 .env가 Gemini여도 mock으로 네 개 개념 검증 통과. Python compile·git diff whitespace 검사도 수행했습니다.

기존 `browser_smoke.py`, `browser_phase2.py`도 mock 서버에서 모두 통과했습니다. 원본 수학·사회 조작·영상 재생, 업로드·PDF·확인 문제·격리·오류 fallback·모바일 화면을 확인했으며 실제 API는 호출하지 않았습니다.

이번 Phase 3-A 검증에서는 **실제 Gemini API 호출을 수행하지 않았습니다.** 무료 할당량을 소비하지 않도록 HTTP 대역을 사용했습니다. 새 DSL의 실제 모델 응답 품질·큰 union 스키마 수용 여부·실제 내레이션 발화 시간은 미확인입니다. `--live` 스크립트가 이를 명시적으로 확인하는 진입점이며 자동 재시도는 없습니다.

## 완료 및 후속 경계

서로 다른 개념의 검증된 JSON, 6종 타입 제약, 향후 렌더러 계약, 기존 테스트 유지와 문서화를 완료했습니다. 자연어 사실성 전체·실제 렌더링·TTS 길이·공개 학생 서비스 적합성을 검증했다고 주장하지 않습니다.

다음 단계에서는 소유한 HTML/SVG 템플릿으로만 이 DSL을 해석하고, 텍스트 넘침·모션·프레임·음성 길이·MP4를 별도로 검증해야 합니다. 지금은 새 영상 다운로드 URL이나 생성 완료 상태를 반환하지 않습니다.
