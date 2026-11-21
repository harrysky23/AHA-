"""Opt-in real API/UI check using one synthetic PDF/question, then a cache hit."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from pdf_fixture import pdf_bytes

ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('AHA_BASE_URL','http://127.0.0.1:8765')
OUT=ROOT/'tmp/screenshots';OUT.mkdir(parents=True,exist_ok=True)


def run():
    with sync_playwright() as p:
        chrome=os.environ.get('AHA_BROWSER_EXECUTABLE','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        browser=p.chromium.launch(executable_path=chrome if Path(chrome).exists() else None,headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        page.goto(BASE)
        expect(page.locator('#generation-mode')).to_contain_text('Gemini AI')
        page.locator('#concept').fill('등속 운동에서 시간과 이동 거리')
        page.locator('#question').fill('시간을 두 배로 늘리면 왜 이동 거리가 두 배가 되나요? 자료를 인용하고 그래프의 시간 값을 바꾸며 실습할 수 있게 설명해 주세요.')
        page.locator('#material').set_input_files({'name':'synthetic-motion.pdf','mimeType':'application/pdf',
            'buffer':pdf_bytes('At a constant speed of 2 meters per second, distance equals 2 times the elapsed time.')})
        page.locator('#external-consent').check()
        with page.expect_response(lambda r:r.url.endswith('/api/learn'),timeout=110000) as response_info:
            page.locator('#generate').click()
        response=response_info.value
        data=response.json()
        if response.status!=200:
            print('Actual FastAPI request failed:',response.status,data.get('code'),data.get('detail'))
            browser.close();return 1
        assert data['mode']=='gemini' and data['generation']['status']=='validated'
        assert data['lesson']['viewer_url']=='/lessons/interactive'
        spec=data['lesson']['spec']
        assert spec['source_quotes']
        assert spec['visualization']['type']=='function_graph'
        frame=page.frame_locator('#lesson-view iframe')
        expect(frame.locator('#practice')).to_be_visible()
        expect(frame.locator('#explanation')).to_have_text(spec['explanation'])
        before=frame.locator('#visual .detail').inner_text()
        frame.locator('#graph-control').fill('150')
        assert frame.locator('#visual .detail').inner_text()!=before
        frame.locator('#quiz-options button').nth(spec['quiz']['correct_index']).click()
        expect(frame.locator('#quiz-result')).to_contain_text('정답이에요')
        frame.locator('#visual').scroll_into_view_if_needed()
        page.screenshot(path=str(OUT/'gemini-live-graph.png'))
        page.locator('#edit-input').click()
        with page.expect_response(lambda r:r.url.endswith('/api/learn'),timeout=110000) as cached_response_info:
            page.locator('#generate').click()
        cached_response=cached_response_info.value
        cached=cached_response.json()
        assert cached_response.status==200 and cached['generation']['cached'] is True
        assert cached['generation']['usage']=={}
        assert cached['lesson']['spec']==data['lesson']['spec']
        expect(page.locator('#result-mode')).to_contain_text('캐시 재사용')
        evidence={'timestamp_utc':datetime.now(timezone.utc).isoformat(),
            'provider':data['mode'],'model':data['generation']['model'],
            'fresh_generation_confirmed':not data['generation']['cached'],
            'cache_reuse_confirmed':True,'pdf_text_extracted':data['grounding']['extracted_characters'],
            'source_quotes_checked':len(spec['source_quotes']),
            'graph_slider_changed':True,
            'quiz_feedback_checked':True,
            'request_ids':[data['generation']['request_id'],cached['generation']['request_id']],
            'explanation_sha256':hashlib.sha256(data['lesson']['spec']['explanation'].encode()).hexdigest()}
        (ROOT/'tmp/gemini-live-ui.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
        browser.close()
        print('PASS real Gemini -> FastAPI -> PDF-grounded JSON -> isolated graph -> repeat cache hit')
        print('Fresh generation:',evidence['fresh_generation_confirmed'],'model:',evidence['model'])
        return 0


if __name__=='__main__':
    print('Explicit live check: sends a synthetic question/PDF to Gemini. One additional call is possible on model overload.')
    raise SystemExit(run())
