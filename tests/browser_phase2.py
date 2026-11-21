"""Phase 2 UI checks against mock mode. No real external API calls."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from pdf_fixture import pdf_bytes

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/screenshots';OUT.mkdir(parents=True,exist_ok=True)
BASE=os.environ.get('AHA_BASE_URL','http://127.0.0.1:8766')


def generate(page,question):
    page.locator('#question').fill(question)
    page.locator('#generate').click()
    frame=page.frame_locator('#lesson-view iframe')
    expect(frame.locator('#dynamic-lesson')).to_be_visible()
    return frame


with sync_playwright() as p:
    chrome=os.environ.get('AHA_BROWSER_EXECUTABLE','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    browser=p.chromium.launch(executable_path=chrome if Path(chrome).exists() else None,headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(BASE)
    expect(page.locator('#generation-mode')).to_contain_text('mock')
    page.locator('#concept').fill('미분계수')
    page.locator('#material').set_input_files({'name':'study.pdf','mimeType':'application/pdf','buffer':pdf_bytes('For f(x)=x squared, the secant slope is 2+h when h is nonzero.')})
    frame=generate(page,'h=0을 바로 대입하면 왜 안 되나요?')
    expect(page.locator('#grounding-note')).to_contain_text('추출했어요')
    expect(page.locator('#result-mode')).to_contain_text('mock')
    expect(frame.locator('#h-value')).to_have_text('1.2000')
    zero_explanation=frame.locator('#lesson-explanation').inner_text()
    frame.locator('#source-details summary').click()
    expect(frame.locator('#source-quotes')).to_contain_text('the secant slope is 2+h')
    frame.locator('#answer-0').fill('2.1')
    frame.get_by_role('button',name='답 확인').first.click()
    expect(frame.locator('.quiz-feedback').first).to_contain_text('맞았어요')
    frame.locator('#answer-1').select_option('undefined')
    frame.get_by_role('button',name='답 확인').nth(1).click()
    expect(frame.locator('.quiz-feedback').nth(1)).to_contain_text('맞았어요')
    page.locator('#learning-result').evaluate('(el)=>el.scrollIntoView({block:"start"})')
    page.screenshot(path=str(OUT/'phase2-pdf-desktop.png'))
    print('PASS actual PDF text -> structured mock lesson -> examples/quiz/source quote')

    page.locator('#edit-input').click()
    frame=generate(page,'음수 h에서 왼쪽으로 접근해도 접선이 되나요?')
    expect(frame.locator('#h-value')).to_have_text('1.2000')
    assert frame.locator('#lesson-explanation').inner_text()==zero_explanation
    frame.locator('#delta').fill('-0.1')
    expect(frame.locator('#secant-value')).to_have_text('1.9000')
    rendered_slope=frame.locator('#secant-line').evaluate('(line)=>-(Number(line.getAttribute("y2"))-Number(line.getAttribute("y1")))/(Number(line.getAttribute("x2"))-Number(line.getAttribute("x1")))*120/44')
    assert abs(rendered_slope-1.9)<1e-7
    expect(frame.locator('#analysis-level')).to_contain_text('기초부터')
    frame.locator('#delta').fill('0.0001')
    expect(frame.locator('#secant-value')).to_have_text('2.0001')
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#lesson-view iframe').scroll_into_view_if_needed()
    assert frame.locator('body').evaluate('async () => {for(let i=0;i<120;i++){if(document.documentElement.scrollHeight<=innerHeight+2)return true;await new Promise(r=>setTimeout(r,20));}return false;}')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert frame.locator('body').evaluate('() => document.documentElement.scrollWidth<=innerWidth')
    frame.locator('#quiz-items').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'phase2-quiz-mobile.png'))
    print('PASS mock stays fixed across questions; signed slider geometry and mobile sizing')

    page.locator('#edit-input').click()
    page.locator('#material').set_input_files({'name':'scan-or-blank.pdf','mimeType':'application/pdf','buffer':pdf_bytes(text=None)})
    frame=generate(page,'할선이 무엇인가요?')
    expect(page.locator('#grounding-note')).to_contain_text('OCR은 지원하지 않아')
    expect(frame.locator('#source-details')).to_be_hidden()
    page.locator('#edit-input').click()
    page.locator('#material').set_input_files({'name':'broken.pdf','mimeType':'application/pdf','buffer':b'%PDF-broken'})
    page.locator('#generate').click()
    expect(page.locator('#request-error')).to_contain_text('PDF를 읽지 못했어요')
    expect(page.locator('#fallback')).to_be_visible()
    page.locator('#fallback').click()
    frame=page.frame_locator('#lesson-view iframe')
    expect(frame.locator('#secant-value')).to_have_text('3.2000')
    print('PASS textless/corrupt PDF notices and original demo fallback')

    # UI-only Gemini mode simulation. HTTP is intercepted and never contacts Google.
    page.route('**/api/health',lambda r:r.fulfill(json={'status':'ok','mode':'gemini','external_ai':True,'ai_configured':True,'request_timeout_seconds':60}))
    requests=[]
    def limited(route):
        requests.append(route.request)
        route.fulfill(status=429,json={'detail':'테스트: 호출 한도 도달','code':'gemini_quota_exceeded','fallback_available':True})
    page.route('**/api/learn',limited)
    page.reload()
    expect(page.locator('#generation-mode')).to_contain_text('Gemini AI')
    page.locator('#sample-input').click()
    page.locator('#generate').click()
    expect(page.locator('#request-error')).to_contain_text('전송 안내')
    assert not requests
    page.locator('#external-consent').check()
    page.locator('#generate').click()
    expect(page.locator('#request-error')).to_contain_text('호출 한도')
    assert len(requests)==1
    assert b'name="consent"' in requests[0].post_data_buffer
    page.locator('#fallback').click()
    expect(page.frame_locator('#lesson-view iframe').locator('#secant-value')).to_have_text('3.2000')
    print('PASS Gemini UI consent and simulated rate-limit fallback (not a live API call)')
    assert not errors,errors
    browser.close()
print('All Phase 2 browser checks passed.')
