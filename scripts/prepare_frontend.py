"""Rebuild index from the untouched reference and the additive workflow section."""
import base64
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
source = next((ROOT / "references").glob("*.html"))
html = source.read_text()
media = ROOT / "frontend/static/media"
media.mkdir(parents=True, exist_ok=True)
videos = [("derivative-explainer.mp4", "video[data-embed]", "embed"),
          ("supply-demand-explainer.mp4", "video[data-embed-econ]", "embedEcon")]
matches = list(re.finditer(r'<script>\s*/\*[^*]*\*/\s*\(function\(\)\{\s*const B64="([^"]+)";.*?</script>', html, re.S))
if len(matches) != 2:
    raise RuntimeError("Expected the original two embedded video scripts")
for match, (filename, selector, dataset) in reversed(list(zip(matches, videos))):
    (media / filename).write_bytes(base64.b64decode(match.group(1), validate=True))
    replacement = f'''<script>
document.querySelectorAll('{selector}').forEach(v => {{
  const t = +v.dataset.{dataset};
  v.src = '/static/media/{filename}' + (t ? '#t=' + t : '');
  if (v.autoplay) v.play().catch(() => {{}});
}});
</script>'''
    html = html[:match.start()] + replacement + html[match.end():]
html = html.replace('</head>', '<link rel="stylesheet" href="/static/workflow.css">\n</head>')
html = html.replace('<section class="final" id="start">', (ROOT / 'frontend/workflow.html').read_text() + '\n<section class="final" id="start">')
html = html.replace('href="#start"', 'href="#learn"').replace('href="#">내 자료로 시작하기', 'href="#learn">내 자료로 시작하기')
html = html.replace('체험해 보기</a>', '기존 데모 보기</a>')
# Keep the design, clarify capability claims in the served Phase 1 copy only.
html = html.replace('AI가 자료를 분석', '학습 방식 선택').replace('내 교재의 용어·예제·난이도를 읽고, 어디서 막혔는지에 맞춰 설명 흐름을 설계해요.', '인터랙티브 학습 또는 기존 영상 예시를 골라요. 현재 자료 분석과 AI 생성은 준비 중이에요.')
html = html.replace('인터랙티브 학습 + 숏츠', '예제로 학습 시작').replace('직접 움직여 보는 학습 페이지와, 음성 해설이 담긴 짧은 개념 영상을 받아요.', '수학 II 고정 예제를 조작하거나, 시안에 포함된 기존 영상을 볼 수 있어요.')
html = html.replace('우리 학교 교재·선생님 필기 표현 그대로', '목표 기능 · 자료 분석은 준비 중').replace('기초부터 심화까지 설명 수준 조절', '목표 기능 · 현재는 고정 예제').replace('“예시를 하나 더” 같은 요청을 바로 반영', '목표 기능 · 후속 질문은 준비 중')
html = html.replace('<h4>TTS 음성 해설</h4>', '<h4>기존 영상의 음성 해설</h4>')
html = html.replace('class="tag">음성 해설', 'class="tag">기존 예시 영상')
html = html.replace('<body>', '<body>\n<div class="phase-banner">로컬 PoC · 수학 II 고정 예제와 기존 영상으로 체험합니다. 자료 분석·AI 생성·새 숏츠 생성은 준비 중입니다.</div>')
html = html.replace('</body>', '<script src="/static/workflow.js" defer></script>\n</body>')
(ROOT / 'frontend/index.html').write_text(html)
print('Reference SHA256:', hashlib.sha256(source.read_bytes()).hexdigest())
print('Created frontend/index.html and extracted two original MP4 assets')
