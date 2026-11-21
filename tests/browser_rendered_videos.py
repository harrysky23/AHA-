"""Opt-in playback of existing local MP4 outputs. Never creates media/AI calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from playwright.sync_api import sync_playwright
from backend.app.rendering.browser import browser_executable

parser=argparse.ArgumentParser(description='Chrome으로 기존 로컬 MP4의 로드·탐색·재생 검증')
parser.add_argument('directory',nargs='?',type=Path,default=ROOT/'tmp/videos/phase3b')
args=parser.parse_args()
files=sorted(args.directory.glob('*.mp4'))
assert files,'먼저 render_storyboard.py로 MP4를 생성하세요.'
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=browser_executable(),headless=True)
    context=browser.new_context(offline=True,service_workers='block')
    page=context.new_page()
    for path in files:
        page.goto(path.resolve().as_uri())
        page.wait_for_function('() => {const v=document.querySelector("video");return v&&v.readyState>=2}',timeout=15000)
        info=page.locator('video').evaluate('''async v=>{
          v.muted=true;v.currentTime=5;
          await new Promise((resolve,reject)=>{v.addEventListener('seeked',resolve,{once:true});v.addEventListener('error',reject,{once:true});});
          await v.play();
          return {width:v.videoWidth,height:v.videoHeight,duration:v.duration,start:v.currentTime};
        }''')
        page.wait_for_function('(start)=>document.querySelector("video").currentTime>start+.3',arg=info['start'],timeout=10000)
        assert info['width']/info['height']==9/16 and 29.9<=info['duration']<=60.1
        assert page.locator('video').evaluate('(v)=>v.error===null')
        page.locator('video').evaluate('(v)=>v.pause()')
        results.append({'file':path.name,**info,'playback':'passed'})
    browser.close()
out=ROOT/'tmp/rendering-checks';out.mkdir(parents=True,exist_ok=True)
(out/'playback.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False))
