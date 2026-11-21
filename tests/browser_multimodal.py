"""Explicit offline real-browser overlay checks, no provider or TTS calls."""
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.rendering.browser import FrameRenderer
from backend.app.rendering.core import Budget, RenderOptions
from scripts.compare_water_cycle import water_storyboard

out=ROOT/"tmp/rendering-checks";out.mkdir(exist_ok=True,parents=True)
checks=[]
with tempfile.TemporaryDirectory() as directory:
    budget=Budget(Path(directory),RenderOptions(fps=3))
    with FrameRenderer(water_storyboard(),budget,layered=True) as renderer:
        for mode in [False,True]:
            png,state=renderer.frame(2.5,subtitle="안전한 한국어 자막 <script> 문자를 그대로 표시해요.",text_motion=mode)
            again,_=renderer.frame(2.5,subtitle="안전한 한국어 자막 <script> 문자를 그대로 표시해요.",text_motion=mode)
            assert png==again and not state["overflow"]
            assert renderer.page.locator("script").count()==1
            assert renderer.page.evaluate("() => getComputedStyle(document.getElementById('stage')).backgroundColor==='rgba(0, 0, 0, 0)'")
            assert renderer.page.evaluate("""() => {
                const ids=['title','visual-card','notes','subtitle'];
                const r=ids.map(id=>document.getElementById(id).getBoundingClientRect());
                return r.every(x=>x.left>=0&&x.right<=1080&&x.top>=0&&x.bottom<=1920)&&r.every((x,i)=>!i||r[i-1].bottom<=x.top);
            }""")
            assert renderer.blocked_requests==0
            (out/("overlay-text.png" if mode else "overlay-svg.png")).write_bytes(png)
            checks.append({"text_motion":mode,"deterministic":True,"layout":"passed","network_requests":0})
(out/"multimodal-checks.json").write_text(json.dumps(checks,indent=2))
print(json.dumps(checks))
