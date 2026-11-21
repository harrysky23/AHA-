"""Run against a running local server: python tests/browser_smoke.py."""
import base64
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp/screenshots'
OUT.mkdir(parents=True, exist_ok=True)
BASE_URL = os.environ.get('AHA_BASE_URL', 'http://127.0.0.1:8765')
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')


def check_existing_demos(page):
    expect(page.locator('#sec')).to_have_text('3.20')
    page.locator('#hRange').fill('0')
    expect(page.locator('#sec')).to_have_text('2.01')
    page.get_by_role('tab', name='사회 · 수요와 공급').click()
    page.get_by_role('button', name='흉년이 들면').click()
    expect(page.locator('#eP')).to_have_text('6.5')
    expect(page.locator('#eQ')).to_have_text('2.5')
    page.get_by_role('button', name='처음으로', exact=True).click()
    expect(page.locator('#eP')).to_have_text('5.0')
    page.get_by_role('tab', name='수학 · 미분계수의 기하학적 의미').click()


with sync_playwright() as p:
    chrome = os.environ.get('AHA_BROWSER_EXECUTABLE', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    browser = p.chromium.launch(executable_path=chrome if Path(chrome).exists() else None, headless=True)
    page = browser.new_page(viewport={'width':1440, 'height':1000}, reduced_motion='reduce')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(next((ROOT / 'references').glob('*.html')).resolve().as_uri())
    page.screenshot(path=str(OUT / 'baseline-desktop.png'))
    check_existing_demos(page)
    print('PASS original math and economics demos')

    page.goto(BASE_URL)
    page.screenshot(path=str(OUT / 'phase1-landing.png'))
    check_existing_demos(page)
    page.get_by_role('link', name='내 자료로 시작하기 →').first.click()
    expect(page).to_have_url(BASE_URL + '/#learn')
    page.locator('#generate').click()
    expect(page.locator('#request-error')).to_contain_text('개념 또는 질문')
    page.locator('#sample-input').click()
    page.locator('#material').set_input_files({'name':'필기.png','mimeType':'image/png','buffer':PNG})
    page.locator('#generate').click()
    expect(page.locator('#learning-result')).to_be_visible()
    expect(page.locator('#request-summary')).to_contain_text('필기.png')
    expect(page.locator('#grounding-note')).to_contain_text('이미지 OCR은 아직 지원하지 않아요')
    iframe = page.locator('#lesson-view iframe')
    expect(iframe).to_have_attribute('sandbox', 'allow-scripts')
    lesson = page.frame_locator('#lesson-view iframe')
    expect(lesson.locator('#secant-value')).to_have_text('3.2000')
    for h, slope in [('0.1','2.1000'),('0.01','2.0100'),('0.0001','2.0001'),('-0.1','1.9000')]:
        lesson.locator(f'[data-h="{h}"]').click()
        expect(lesson.locator('#secant-value')).to_have_text(slope)
    lesson.get_by_role('button',name='0은 어떨까?').click()
    expect(lesson.locator('#secant-value')).to_have_text('정의 안 됨')
    expect(lesson.locator('#insight')).to_contain_text('극한')
    assert iframe.content_frame.locator('body').evaluate("() => {try {return !!parent.document.body;} catch(e) {return false;}}") is False
    page.screenshot(path=str(OUT / 'phase1-result-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#learning-result').evaluate('(el)=>el.scrollIntoView({block:"start"})')
    page.screenshot(path=str(OUT / 'phase1-result-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert lesson.locator('body').evaluate('() => document.documentElement.scrollWidth <= innerWidth')
    page.wait_for_function("(() => {const f=document.querySelector('#lesson-view iframe');return parseFloat(f.style.height)>1200;})()")
    iframe.scroll_into_view_if_needed()
    assert lesson.locator('body').evaluate('async () => {for(let i=0;i<120;i++){if(document.documentElement.scrollHeight<=innerHeight+2)return true;await new Promise(r=>setTimeout(r,20));}return false;}')
    page.set_viewport_size({'width':1440,'height':1000})
    expect(lesson.locator('#dynamic-lesson')).to_be_visible()
    print('PASS upload -> API -> isolated lesson, signed h and zero')

    page.locator('#edit-input').click()
    page.get_by_role('radio',name='숏츠 학습',exact=False).check()
    page.locator('#generate').click()
    expect(page.locator('#video-view')).to_be_visible()
    expect(page.locator('#video-note')).to_contain_text('새로 만든 9:16 숏츠가 아니며')
    page.wait_for_function("document.querySelector('#result-video').readyState >= 2")
    metadata = page.locator('#result-video').evaluate('(v)=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration})')
    assert metadata['width'] > metadata['height'] > 0
    page.locator('#result-video').evaluate('(v)=>{v.muted=true;return v.play()}')
    page.wait_for_function("document.querySelector('#result-video').currentTime > 0")
    page.locator('#result-video').evaluate('(v)=>v.pause()')
    page.locator('#switch-html').click()
    expect(page.locator('#lesson-view iframe')).to_be_visible()
    print('PASS existing sample video playback and return to lesson',metadata)

    page.locator('#edit-input').click()
    page.locator('#question').fill('<img src=x onerror=alert(1)>')
    page.locator('#generate').click()
    expect(page.locator('#request-summary')).to_contain_text('<img src=x onerror=alert(1)>')
    assert page.locator('#request-summary img').count() == 0
    page.locator('#edit-input').click()
    page.route('**/api/learn',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"테스트 오류"}'))
    page.locator('#generate').click()
    expect(page.locator('#fallback')).to_be_visible()
    page.locator('#fallback').click()
    expect(page.locator('#result-mode')).to_contain_text('API 연결 없이')
    expect(lesson.locator('#secant-value')).to_have_text('3.2000')
    page.unroute('**/api/learn')
    page.locator('#edit-input').click()
    page.route('**/api/learn',lambda route:route.abort('failed'))
    page.locator('#generate').click()
    expect(page.locator('#request-error')).to_contain_text('연결하지 못했거나')
    page.locator('#fallback').click()
    expect(lesson.locator('#secant-value')).to_have_text('3.2000')
    page.unroute('**/api/learn')
    print('PASS literal user text, API 503 and disconnected fallback')

    page.set_viewport_size({'width':390,'height':844})
    page.locator('#edit-input').click()
    page.locator('#sample-input').click()
    page.locator('#learn').evaluate('(el)=>el.scrollIntoView({block:"start"})')
    page.screenshot(path=str(OUT / 'phase1-workflow-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert lesson.locator('body').evaluate('() => document.documentElement.scrollWidth <= innerWidth')
    print('PASS mobile viewport without horizontal overflow')
    assert errors == [], errors
    browser.close()
print('All browser smoke checks passed. Screenshots:', OUT)
