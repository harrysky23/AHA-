"""Explicit offline Chromium checks. python tests/browser_rendering.py.

No Gemini, speech or MP4 encoding; real browser frames for all six DSL types.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from backend.app.providers.base import StoryboardInput
from backend.app.rendering.browser import FrameRenderer
from backend.app.rendering.core import Budget, RenderOptions
from backend.app.services.materials import MaterialContext
from backend.app.services.storyboard_mock import (generate_mock_storyboard,function_graph,water_cycle,timeline,comparison,binary_search,text_explanation)
from backend.app.storyboard_schema import StoryboardSpec

OUT=ROOT/'tmp/rendering-checks'
OUT.mkdir(parents=True,exist_ok=True)
BASE=generate_mock_storyboard(StoryboardInput('미분계수','변화 원리를 설명해 주세요.',MaterialContext())).model_dump()


def spec(visual):
    data=deepcopy(BASE);data['scenes'][0]['visualization']=visual
    data['scenes'][0]['screen']['title']='시각화 렌더러 확인'
    return StoryboardSpec.model_validate(data)


checks=[]
with tempfile.TemporaryDirectory() as directory:
    budget=Budget(Path(directory),RenderOptions(preview=True,fps=3))
    for factory in [function_graph,water_cycle,timeline,comparison,binary_search,text_explanation]:
        value=spec(factory())
        with FrameRenderer(value,budget) as renderer:
            png,state=renderer.frame(2.5)
            again,_=renderer.frame(2.5)
            if png!=again:
                (OUT/'difference-first.png').write_bytes(png);(OUT/'difference-second.png').write_bytes(again)
            assert png==again,f'{factory.__name__}: Same specification/time must produce identical PNG bytes'
            assert not state['overflow'] and not state['fallbacks'],state
            (OUT/f'{value.scenes[0].visualization.type}.png').write_bytes(png)
            if factory==function_graph:
                q=state['markers']['q'];assert abs(q['x']-1.505)<1e-8 and abs(q['y']-q['x']**2)<1e-8
                changed,_=renderer.frame(4.5);assert changed!=png
                renderer.frame(.1);back,_=renderer.frame(2.5);assert back==png
            if factory==binary_search:
                assert state['state_id']=='full'
                assert renderer.frame(3.5)[1]['state_id']=='right'
                assert renderer.frame(7)[1]['state_id']=='found'
            assert renderer.blocked_requests==0
            checks.append({'type':value.scenes[0].visualization.type,'deterministic':True,'layout':'passed','sha256':hashlib.sha256(png).hexdigest()})
    with FrameRenderer(spec(function_graph()),budget) as renderer:
        png,_=renderer.frame(2.5)
        assert png==(OUT/'function_graph.png').read_bytes(),'Independent browser runs must match'
    value=spec(water_cycle()).model_dump()
    for node in value['scenes'][0]['visualization']['nodes']:node.update(x=.5,y=.5)
    with FrameRenderer(StoryboardSpec.model_validate(value),budget) as renderer:
        png,state=renderer.frame(2)
        assert state['fallbacks']=={'scene_1':'overlapping_nodes'} and not state['overflow']
        (OUT/'fallback.png').write_bytes(png)
        checks.append({'fallback':'overlapping_nodes','scene_id':'scene_1'})
    value=spec(function_graph()).model_dump()
    value['scenes'][0]['screen']['title']='긴 한국어 문장의 배치와 안전 영역을 확인해요 '*4
    value['scenes'][0]['screen']['title']=value['scenes'][0]['screen']['title'][:80]
    value['scenes'][0]['screen']['bullets']=['아주 긴 한국어 학습 설명 문장을 안전하게 여러 페이지로 나누어 표시합니다. '*7][:1]
    value['scenes'][0]['screen']['bullets'][0]=value['scenes'][0]['screen']['bullets'][0][:280]
    value['scenes'][0]['narration_ko']='학생이 읽을 수 있도록 한국어 내레이션을 잘라 표시하고 화면 밖으로 나가지 않게 합니다. '*8
    value['scenes'][0]['screen']['formulas']=['<img src="https://invalid.example/" onerror="alert(1)">']
    value['scenes'][0]['cues']=[{'at_seconds':0.,'action':'hide','target_id':'p'},{'at_seconds':1.,'action':'reveal','target_id':'p'},{'at_seconds':2.,'action':'highlight','target_id':'p'}]
    with FrameRenderer(StoryboardSpec.model_validate(value),budget) as renderer:
        for t in [.5,1.5,2.5,5.,9.]:
            png,state=renderer.frame(t);assert not state['overflow']
            assert renderer.page.evaluate("() => ['title','notes','subtitle'].every(id=>{const e=document.getElementById(id);return e.scrollHeight<=e.clientHeight+1&&e.scrollWidth<=e.clientWidth+1})")
            marker=renderer.page.locator('[data-element-id="p"]').first
            assert marker.evaluate('(el)=>el.style.opacity')==('0' if t==.5 else '1')
            if t>=2.5:assert 'drop-shadow' in marker.evaluate('(el)=>el.style.filter')
        assert renderer.page.locator('img').count()==0
        assert renderer.blocked_requests==0
        (OUT/'long-korean-literal-markup.png').write_bytes(png)
        assert renderer.page.evaluate("() => fetch('https://invalid.example').then(()=>false,()=>true)")
        try:renderer.page.goto('https://invalid.example/',timeout=1500)
        except Exception:pass
        assert renderer.blocked_requests>=1
        checks.append({'long_korean':'passed','markup':'literal_text','network':'blocked','cues':'rendered'})
(OUT/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
print(json.dumps({'checks':checks,'output':str(OUT)},ensure_ascii=False))
