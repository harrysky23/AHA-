"""Opt-in actual local rendering through the web. Mock AI only, real MP4/TTS.

Start a mock server with AHA_VIDEO_PREVIEW=true AHA_VIDEO_FPS=3, then run.
"""
import json
import os
from pathlib import Path
import sys
import time

import psutil
from playwright.sync_api import expect, sync_playwright
from pdf_fixture import pdf_bytes

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.rendering.browser import browser_executable

BASE=os.environ.get('AHA_BASE_URL','http://127.0.0.1:8766')
OUT=ROOT/'tmp/phase3c-checks';OUT.mkdir(parents=True,exist_ok=True)


def wait_job(context,id,predicate,limit=180):
    deadline=time.monotonic()+limit
    while time.monotonic()<deadline:
        response=context.request.get(f'{BASE}/api/videos/{id}')
        assert response.ok,response.text()
        data=response.json()
        if predicate(data):return data
        assert data['status'] not in {'failed','cancelled'},data
        time.sleep(.25)
    raise AssertionError('job wait timed out')


def owned_worker(id):
    for process in psutil.process_iter(['pid','cmdline']):
        try:
            command=process.info['cmdline'] or []
            if 'backend.app.rendering.worker' in command and any(id in part for part in command):
                return process
        except psutil.NoSuchProcess:pass
    raise AssertionError('renderer worker was not found')


with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=browser_executable(),headless=True)
    context=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce',accept_downloads=True)
    assert context.request.get(BASE+'/api/health').json()['mode']=='mock','Only a mock server is permitted'
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(BASE)
    expect(page.locator('#generation-mode')).to_contain_text('mock')
    page.locator('#concept').fill('물의 순환')
    page.locator('#question').fill('증발과 응결이 어떻게 연결되나요?')
    page.locator('#material').set_input_files({'name':'water-study.pdf','mimeType':'application/pdf',
        'buffer':pdf_bytes('Water evaporates, condenses and returns as precipitation.')})
    page.locator('[name=format][value=shorts]').check()
    page.locator('#video-duration').select_option('30')
    page.locator('#generate').click()
    expect(page.locator('#video-job')).to_be_visible()
    page.wait_for_function("/^[a-f0-9]{32}$/.test(localStorage.getItem('aha:video-job')||'')")
    id=page.evaluate("localStorage.getItem('aha:video-job')")
    assert len(id)==32
    state=wait_job(context,id,lambda d:d['status']=='rendering')
    assert state['video_url'] is None
    page.locator('#video-job').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'generating-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.reload()
    expect(page.locator('#video-job')).to_be_visible()
    assert page.evaluate("localStorage.getItem('aha:video-job')")==id
    complete=wait_job(context,id,lambda d:d['status']=='completed')
    expect(page.locator('#generated-video-view')).to_be_visible(timeout=10000)
    page.wait_for_function("document.querySelector('#generated-video').readyState>=2")
    metadata=page.locator('#generated-video').evaluate('(v)=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration})')
    assert metadata['width']/metadata['height']==9/16 and abs(metadata['duration']-30)<.1
    assert complete['result']['mode']=='mock' and complete['result']['grounding']['status']=='text_extracted'
    page.locator('#generated-video').evaluate('(v)=>{v.muted=true;return v.play()}')
    page.wait_for_function("document.querySelector('#generated-video').currentTime>.3")
    page.locator('#generated-video').evaluate('(v)=>v.pause()')
    page.locator('#generated-video-view').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'completed-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    url=BASE+complete['video_url']
    part=context.request.get(url,headers={'Range':'bytes=0-31'})
    assert part.status==206 and len(part.body())==32 and b'ftyp' in part.body()
    foreign=browser.new_context()
    assert foreign.request.get(url).status==404
    assert foreign.request.get(BASE+'/api/videos/'+id).status==404
    foreign.close()
    with page.expect_download() as info:page.locator('#video-download').click()
    download=info.value;download.save_as(str(OUT/'web-generated.mp4'))
    assert download.failure() is None and (OUT/'web-generated.mp4').stat().st_size>1000
    page.reload();expect(page.locator('#generated-video-view')).to_be_visible(timeout=10000)
    # Existing HTML learning remains available after a real video completes.
    page.locator('#sample-input').click();page.locator('[name=format][value=html]').check();page.locator('#generate').click()
    expect(page.frame_locator('#lesson-view iframe').locator('#secant-value')).to_have_text('3.2000')
    print('PASS actual PDF → mock storyboard → real MP4 → reload recovery → mobile playback/Range/download/ownership → HTML')

    # Actual worker + detached browser cleanup. Wait for capture before cancelling.
    response=context.request.post(BASE+'/api/videos',multipart={'concept':'이진 탐색','target_duration_seconds':'30'})
    assert response.status==202,response.text()
    cancel_id=response.json()['job_id']
    wait_job(context,cancel_id,lambda d:d['stage']=='frames' and d['progress'].get('frames_done',0)>0)
    worker=owned_worker(cancel_id)
    processes=[worker,*worker.children(recursive=True)]
    identities=[(proc.pid,proc.create_time())for proc in processes]
    queued=context.request.post(BASE+'/api/videos',multipart={'concept':'미분계수','target_duration_seconds':'30'})
    assert queued.status==202
    queued_id=queued.json()['job_id']
    assert context.request.delete(BASE+'/api/videos/'+queued_id).json()['status']=='cancelled'
    result=context.request.delete(BASE+'/api/videos/'+cancel_id)
    assert result.status in {200,202}
    cancelled=wait_job(context,cancel_id,lambda d:d['status']=='cancelled',limit=20)
    assert cancelled['video_url'] is None
    for pid,created in identities:
        try:
            proc=psutil.Process(pid)
            assert proc.create_time()!=created or proc.status()==psutil.STATUS_ZOMBIE,(pid,'still running')
        except psutil.NoSuchProcess:pass
    assert not (ROOT/'tmp/video-jobs'/cancel_id).exists()
    print('PASS queued cancellation + actual rendering cancellation and child process cleanup',len(identities),'processes')

    # UI failure state is an explicit HTTP double; no Gemini call.
    fake=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce')
    fp=fake.new_page();fake_id='a'*32
    fp.route('**/api/videos',lambda r:r.fulfill(status=202,json={'job_id':fake_id,'status':'queued','stage':'queued','progress':{},'expires_at':time.time()+120}))
    fp.route('**/api/videos/'+fake_id,lambda r:r.fulfill(json={'job_id':fake_id,'status':'failed','stage':'failed','progress':{},
        'error':{'phase':'generation','code':'gemini_quota_exceeded','message':'테스트용 무료 요청 한도 초과'}}))
    fp.goto(BASE);fp.locator('#sample-input').click();fp.locator('[name=format][value=shorts]').check();fp.locator('#generate').click()
    expect(fp.locator('#video-job-error')).to_contain_text('무료 요청 한도 초과',timeout=10000)
    expect(fp.locator('#video-retry')).to_be_visible();fp.locator('#video-sample').click()
    expect(fp.locator('#video-view')).to_be_visible();expect(fp.locator('#video-note')).to_contain_text('새 생성 아님')
    fp.screenshot(path=str(OUT/'failure-fallback-mobile.png'))
    fake.close()
    assert not errors,errors
    (OUT/'verification.json').write_text(json.dumps({'job_id':id,'status':'completed','mode':'mock','media':metadata,
        'download_bytes':(OUT/'web-generated.mp4').stat().st_size,'cancelled_job':cancel_id,'child_processes_checked':len(identities),
        'mobile':'passed','reload':'passed','range':'passed','ownership':'passed','failure_ui':'HTTP double passed'},ensure_ascii=False,indent=2))
    browser.close()
print('All Phase 3-C browser checks passed. Artifacts:',OUT)
