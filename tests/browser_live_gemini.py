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
        page.locator('#concept').fill('미분계수의 기하학적 의미')
        page.locator('#question').fill('음수 h에서 왼쪽으로 접근해도 할선의 기울기가 2에 가까워지는 이유를 자료의 식과 연결해 설명해 주세요.')
        page.locator('#material').set_input_files({'name':'synthetic-calculus.pdf','mimeType':'application/pdf',
            'buffer':pdf_bytes('For f(x)=x squared at x=1, the secant slope is 2+h for nonzero h. The tangent slope is 2.')})
        page.locator('#external-consent').check()
        with page.expect_response(lambda r:r.url.endswith('/api/learn'),timeout=110000) as response_info:
            page.locator('#generate').click()
        response=response_info.value
        data=response.json()
        if response.status!=200:
            print('Actual FastAPI request failed:',response.status,data.get('code'),data.get('detail'))
            browser.close();return 1
        assert data['mode']=='gemini' and data['verification']['numeric_checks']=='passed'
        assert data['lesson']['spec']['source_quotes']
        frame=page.frame_locator('#lesson-view iframe')
        expect(frame.locator('#dynamic-lesson')).to_be_visible()
        expect(frame.locator('#lesson-explanation')).to_have_text(data['lesson']['spec']['explanation'])
        frame.locator('[data-h="-0.1"]').click()
        expect(frame.locator('#secant-value')).to_have_text('1.9000')
        frame.locator('[data-h="0.0001"]').click()
        expect(frame.locator('#secant-value')).to_have_text('2.0001')
        frame.locator('[data-h="0"]').click()
        expect(frame.locator('#secant-value')).to_have_text('정의 안 됨')
        frame.locator('#graph').scroll_into_view_if_needed()
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
            'new_api_calls':0 if data['generation']['cached'] else 1,
            'cache_reuse_confirmed':True,'pdf_text_extracted':data['grounding']['extracted_characters'],
            'source_quotes_checked':data['verification']['source_quotes'],
            'numeric_checks':data['verification']['numeric_checks'],
            'graph_positive_negative_zero_checked':True,
            'request_ids':[data['generation']['request_id'],cached['generation']['request_id']],
            'explanation_sha256':hashlib.sha256(data['lesson']['spec']['explanation'].encode()).hexdigest()}
        (ROOT/'tmp/gemini-live-ui.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
        browser.close()
        print('PASS real Gemini -> FastAPI -> PDF-grounded JSON -> isolated graph -> repeat cache hit')
        print('New API calls:',evidence['new_api_calls'],'model:',evidence['model'])
        return 0


if __name__=='__main__':
    print('Explicit live check: sends one synthetic question/PDF to Gemini and consumes API quota. No automatic retry.')
    raise SystemExit(run())
