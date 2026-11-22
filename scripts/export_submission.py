"""Package the existing frontend as one local, backend-free submission HTML.

Run: python scripts/export_submission.py [output-directory]
Only explicit frontend assets are included; no environment or backend files.
"""
import base64
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Expected exactly one export anchor: {old[:90]}")
    return text.replace(old, new, 1)


def build() -> str:
    frontend = ROOT / "frontend"
    html = (frontend / "index.html").read_text()
    html = replace_once(html, '<title>아하! · AI 개념 학습 도우미</title>', '<title>아하! · 프론트엔드 제출본</title>')
    html = replace_once(html, '<link rel="stylesheet" href="/static/workflow.css">', '<style>\n' + (frontend / 'static/workflow.css').read_text() + '\n</style>')
    # Optional web fonts retain the original look online; system fonts work offline.
    html = re.sub(r'<script src="/static/(?:workflow|video-jobs)\.js[^\"]*" defer></script>\n?', '', html)
    html = replace_once(html, '서버 모드를 확인 중입니다. 인터랙티브 학습과 세로형 숏츠 생성을 제공합니다.', '프론트엔드 제출본 · 서버·API 키 없이 체험 · AI 분석·새 콘텐츠 생성은 포함되지 않습니다')
    html = replace_once(html, '나의 아하! 찾기 · 로컬 PoC', '나의 아하! 찾기 · 프론트 체험')
    html = replace_once(html, '텍스트 PDF는 최대 20쪽·12,000자를 추출해요. Gemini 인터랙티브 학습에서는 동의한 첨부 사진을 분석할 수 있어요. 스캔 PDF는 PNG나 JPEG로 올려 주세요. 서버는 원본 파일을 보관하지 않으며, 생성 명세를 서버 메모리에 잠시 캐시해요.', '제출본에서는 파일 선택과 파일명·용량 표시만 체험할 수 있어요. PDF 추출·이미지 분석·자료 전송은 수행하지 않아요.')
    html = replace_once(html, '입력한 주제에 맞는 실습을 직접 조작하고 확인 문제를 풀어요.', '미리 준비된 수학 II 할선·접선 그래프를 직접 조작해요.')
    html = replace_once(html, '모드 확인 중 · mock / Gemini', '고정 수학 예제 · 서버 없이 실행')
    html = replace_once(html, '질문과 자료로 구성한 세로형 학습 영상을 만들어요.', '시안에 포함된 미분계수 설명 영상을 시청해요.')
    html = replace_once(html, '스토리보드 → 한국어 음성·애니메이션 → MP4', '기존 예시 영상 · 새 생성 아님')
    html = replace_once(html, 'mock은 고정 예제, Gemini는 실제 모델로 설명을 구성해요. Elice는 향후 연결 예정이에요.', '제출본은 입력한 질문과 관계없이 고정 예제를 보여 줘요. 맞춤 AI 생성은 서버 실행과 API 설정이 필요해요.')
    html = replace_once(html, '서버의 학습 모드를 확인하고 있어요.', '서버나 API 키 없이 예제를 체험할 수 있어요.')
    # Rendering options and provider consent belong to the connected application.
    html, count = re.subn(r'(<div id="shorts-options" hidden>).*?(<button id="shorts-sample")', r'\1\n          <p class="field-note">이 제출본은 기존 예시 영상을 재생해요. 새 영상 생성·음성 합성·MP4 내보내기는 실행하지 않아요.</p>\n          \2', html, count=1, flags=re.S)
    assert count == 1
    html, count = re.subn(r'        <label id="consent-option".*?(?=        <button id="generate")', '', html, count=1, flags=re.S)
    assert count == 1
    html, count = re.subn(r'    <section id="video-job".*?</section>\n', '', html, count=1, flags=re.S)
    assert count == 1
    for id_ in ('fallback', 'use-shorts'):
        html, count = re.subn(r'        <button id="' + id_ + r'".*?</button>\n', '', html, count=1)
        assert count == 1
    html = replace_once(html, '텍스트 PDF 추출 · OCR은 미지원', '제출본 · 파일 선택 화면 체험')
    html = replace_once(html, '질문에서 추정한 설명 수준 반영', '제출본 · 고정 수학 예제 제공')
    html = replace_once(html, '텍스트 PDF와 질문으로 수학 II 설명을 구성해요. mock 고정 예제와 Gemini AI 모드를 구분해요.', '제출본에서는 자료 선택과 질문 입력 흐름을 체험해요. 실제 자료 분석과 맞춤 생성은 서버와 API 연결이 필요해요.')
    html = replace_once(html, '질문별 설명과 수학 II 그래프를 조작하거나, 시안에 포함된 기존 영상을 볼 수 있어요.', '수학 II 고정 예제의 그래프를 조작하거나, 시안에 포함된 기존 영상을 볼 수 있어요.')
    html = replace_once(html, '특히 헷갈리는 부분을 적으면 실습에 반영할 수 있어요.', '제출본에서는 입력 내용을 표시하고 고정 예제를 열어요.') if '특히 헷갈리는 부분을 적으면 실습에 반영할 수 있어요.' in html else html
    lesson = (frontend / 'lessons/secant-tangent.html').read_text()
    csp = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"
    lesson = replace_once(lesson, '<meta charset="utf-8">', '<meta charset="utf-8">\n<meta http-equiv="Content-Security-Policy" content="' + csp + '">')
    assets = {'lesson': base64.b64encode(lesson.encode()).decode()}
    for filename, key in [('derivative-explainer.mp4', 'derivativeVideo'), ('supply-demand-explainer.mp4', 'economicsVideo')]:
        assets[key] = base64.b64encode((frontend / 'static/media' / filename).read_bytes()).decode()
        html = replace_once(html, "'/static/media/" + filename + "'", 'window.AHASubmission.' + key)
    # Preserve the reference's Blob URLs so browsers can seek to the demo offsets.
    asset_script = '''<script>
window.AHASubmission = (() => {
  const assets = ''' + json.dumps(assets, ensure_ascii=True) + ''';
  function videoUrl(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
    return URL.createObjectURL(new Blob([bytes], {type: 'video/mp4'}));
  }
  return {
    lesson: assets.lesson,
    derivativeVideo: videoUrl(assets.derivativeVideo),
    economicsVideo: videoUrl(assets.economicsVideo),
  };
})();
</script>
'''
    html = replace_once(html, '</head>', asset_script + '</head>')
    controller = (ROOT / 'scripts/submission-workflow.js').read_text()
    html = replace_once(html, '</body>', '<script>\n' + controller + '\n</script>\n</body>')
    if 'fetch(' in html or 'src="/static/' in html or 'href="/static/' in html:
        raise ValueError('Submission still depends on backend requests or static routes')
    return html


if __name__ == '__main__':
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'tmp/submission'
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / 'AHA!_프론트엔드_제출.html'
    output.write_text(build(), encoding='utf-8')
    print(f'Exported {output} ({output.stat().st_size:,} bytes)')
