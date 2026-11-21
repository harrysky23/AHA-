"""Offline job/API tests. Render doubles are never counted as real MP4s."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from threading import Event
import time

from fastapi.testclient import TestClient
import pytest

from backend.app import main
from backend.app.config import Settings
from backend.app.rendering.core import RenderError, RenderOptions
from backend.app.routes.videos import COOKIE
from backend.app.services.errors import LearningError
from backend.app.services.storyboard import create_storyboard
from backend.app.services.video_jobs import VideoJobs, owner_digest
from backend.app.video_config import VideoSettings

PAYLOAD=dict(concept='물의 순환',question='증발과 응결을 설명해 주세요.',material=None,file_data=None,
             target_duration_seconds=30,student_level='high_school')
MEDIA=b'unit-test-fixture-not-real-mp4'*16


def policy(tmp_path,**kwargs):
    return VideoSettings(root=tmp_path/'jobs',queue_limit=2,max_jobs=8,ttl_seconds=120,
        render=RenderOptions(preview=True,fps=1,timeout_seconds=10,max_disk_bytes=1024**2,min_free_bytes=0),**kwargs)


def render_double(spec,output,options,*,cancel_event,on_progress):
    on_progress({'phase':'encode','scene_id':None})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(MEDIA)
    output.with_suffix('.render.json').write_text('{}')
    return {'media':{'duration_seconds':spec['duration_seconds'],'width':540,'height':960},'layout':{'fallbacks':{}}}


async def wait_status(manager,id,status):
    async with asyncio.timeout(5):
        while manager.jobs[id].status!=status:
            await asyncio.sleep(.01)
    return manager.jobs[id]


def test_queue_limits_owners_and_retained_records(tmp_path):
    async def run():
        manager=VideoJobs(policy(tmp_path),render=render_double)
        await manager.start()
        try:
            a=manager.submit('one',dict(PAYLOAD),Settings())
            manager.submit('two',dict(PAYLOAD),Settings())
            with pytest.raises(LearningError) as e:manager.submit('three',dict(PAYLOAD),Settings())
            assert e.value.code=='video_queue_full'
            await manager.cancel(manager.jobs[a['job_id']])
            c=manager.submit('three',dict(PAYLOAD),Settings())
            await wait_status(manager,c['job_id'],'completed')
            assert len(manager.jobs)==3
        finally:await manager.close()
    asyncio.run(run())


def test_owner_limit_independent_of_queue(tmp_path):
    async def run():
        manager=VideoJobs(replace(policy(tmp_path),queue_limit=4),render=render_double)
        await manager.start()
        try:
            manager.submit('owner',dict(PAYLOAD),Settings());manager.submit('owner',dict(PAYLOAD),Settings())
            with pytest.raises(LearningError) as e:manager.submit('owner',dict(PAYLOAD),Settings())
            assert e.value.code=='owner_job_limit'
        finally:await manager.close()
    asyncio.run(run())


def test_storage_admission_and_tombstone_capacity(tmp_path):
    async def run():
        manager=VideoJobs(replace(policy(tmp_path),max_jobs=2),render=render_double)
        await manager.start()
        try:
            first=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            await wait_status(manager,first,'completed')
            second=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            await wait_status(manager,second,'completed')
            with pytest.raises(LearningError) as error:manager.submit('other',dict(PAYLOAD),Settings())
            assert error.value.code=='video_queue_full'
            await manager.cancel(manager.jobs[first])
            third=manager.submit('other',dict(PAYLOAD),Settings())['job_id']
            assert first not in manager.jobs and third in manager.jobs
            manager.storage_used=manager.policy.storage_bytes
            with pytest.raises(LearningError) as error:manager.submit('next',dict(PAYLOAD),Settings())
            assert error.value.code=='video_storage_full'
        finally:await manager.close()
    asyncio.run(run())


@pytest.mark.parametrize('failure,expected',[('generation','quota_exceeded'),('rendering','tts_failed')])
def test_generation_vs_render_errors(tmp_path,failure,expected):
    async def fail_generate(*a,**kw):raise LearningError('quota_exceeded','사용량 초과',429)
    def fail_render(*a,**kw):raise RenderError('tts_failed','음성 생성 실패','scene_2')
    async def run():
        manager=VideoJobs(policy(tmp_path),generate=fail_generate if failure=='generation' else create_storyboard,
                          render=fail_render)
        await manager.start()
        try:
            id=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            job=await wait_status(manager,id,'failed')
            assert job.error['phase']==failure and job.error['code']==expected
            assert job.payload is None and job.settings is None and not manager.path(job).exists()
        finally:await manager.close()
    asyncio.run(run())


def test_cancel_generation_cleans_and_does_not_render(tmp_path):
    entered=Event()
    async def slow(*a,**kw):entered.set();await asyncio.sleep(100)
    def forbidden(*a,**kw):raise AssertionError('Must not render cancelled generation')
    async def run():
        manager=VideoJobs(policy(tmp_path),generate=slow,render=forbidden)
        await manager.start()
        try:
            id=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            while not entered.is_set():await asyncio.sleep(.01)
            state=await manager.cancel(manager.jobs[id]);assert state['cancel_requested']
            await wait_status(manager,id,'cancelled')
            assert manager.jobs[id].payload is None
        finally:await manager.close()
    asyncio.run(run())


@pytest.mark.parametrize('late_failure',[False,True])
def test_cancel_wins_render_completion_or_failure_only_after_ack(tmp_path,late_failure):
    entered,release=Event(),Event()
    def render(spec,output,options,**kwargs):
        entered.set();release.wait(4)
        if late_failure:raise RenderError('encode_failed','대역 인코딩 실패')
        return render_double(spec,output,options,**kwargs)
    async def run():
        manager=VideoJobs(policy(tmp_path),render=render)
        await manager.start()
        try:
            id=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            while not entered.is_set():await asyncio.sleep(.01)
            state=await manager.cancel(manager.jobs[id])
            assert state['status']=='rendering' and state['cancel_requested']
            with pytest.raises(LearningError):manager.lease(manager.jobs[id])
            release.set()
            job=await wait_status(manager,id,'cancelled')
            assert not manager.path(job).exists() and manager.public(job)['video_url'] is None
        finally:release.set();await manager.close()
    asyncio.run(run())


def test_cleanup_failure_must_not_claim_cancelled(tmp_path):
    entered=Event()
    def render(*args,cancel_event,**kwargs):
        entered.set();cancel_event.wait(4)
        raise RenderError('cleanup_failed','종료 확인 실패')
    async def run():
        manager=VideoJobs(policy(tmp_path),render=render);await manager.start()
        try:
            id=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            while not entered.is_set():await asyncio.sleep(.01)
            await manager.cancel(manager.jobs[id])
            job=await wait_status(manager,id,'failed');assert job.error['code']=='cleanup_failed'
            with pytest.raises(LearningError) as error:await manager.cancel(job)
            assert error.value.code=='cleanup_failed' and job.status=='failed'
        finally:await manager.close()
    asyncio.run(run())


def test_expiry_and_stream_lease_cleanup(tmp_path):
    now=[1000.]
    async def run():
        manager=VideoJobs(policy(tmp_path),render=render_double,clock=lambda:now[0]);await manager.start()
        try:
            id=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            job=await wait_status(manager,id,'completed')
            path=manager.lease(job);now[0]=job.expires+1
            await manager.sweep()
            with pytest.raises(LearningError):manager.owned(id,'owner')
            assert path.exists() # Already-authorized stream may finish.
            await manager.release(job);await manager.sweep()
            assert not path.exists() and id not in manager.jobs
        finally:await manager.close()
    asyncio.run(run())


def test_max_runtime_signals_renderer_then_fails(tmp_path):
    now=[1000.];entered=Event()
    def render(*a,cancel_event,**kw):
        entered.set();cancel_event.wait(4);raise RenderError('render_cancelled','취소 확인')
    async def run():
        manager=VideoJobs(policy(tmp_path),render=render,clock=lambda:now[0]);await manager.start()
        try:
            id=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            while not entered.is_set():await asyncio.sleep(.01)
            now[0]+=manager.policy.run_seconds+1
            # Keep TTL separate from execution timeout in this fixture.
            manager.jobs[id].expires=now[0]+100
            await manager.sweep();job=await wait_status(manager,id,'failed')
            assert job.error['code']=='video_job_timeout'
        finally:await manager.close()
    asyncio.run(run())


def test_cli_render_lock_busy_is_waited_without_new_generation(tmp_path):
    calls={'generate':0,'render':0}
    async def generate(*a,**kw):calls['generate']+=1;return await create_storyboard(*a,**kw)
    def render(*a,**kw):
        calls['render']+=1
        if calls['render']==1:raise RenderError('render_busy','다른 렌더링')
        return render_double(*a,**kw)
    async def run():
        manager=VideoJobs(policy(tmp_path),generate=generate,render=render);await manager.start()
        try:
            id=manager.submit('owner',dict(PAYLOAD),Settings())['job_id']
            await wait_status(manager,id,'completed');assert calls=={'generate':1,'render':2}
        finally:await manager.close()
    asyncio.run(run())


def test_restart_and_single_service_process(tmp_path):
    async def run():
        p=policy(tmp_path);first=VideoJobs(p,render=render_double);await first.start()
        id=first.submit('owner',dict(PAYLOAD),Settings())['job_id']
        await wait_status(first,id,'completed')
        second=VideoJobs(p,render=render_double)
        with pytest.raises(RuntimeError):await second.start()
        await first.close()
        orphan=p.root/('f'*32);orphan.mkdir();(orphan/'stale.mp4').write_bytes(b'stale')
        third=VideoJobs(p,render=render_double);await third.start()
        try:
            assert not orphan.exists()
            with pytest.raises(LearningError):third.owned(id,'owner')
        finally:await third.close()
    asyncio.run(run())


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'get_video_settings',lambda:policy(tmp_path))
    monkeypatch.setattr(main,'VideoJobs',lambda p:VideoJobs(p,render=render_double))
    with TestClient(main.app) as client:yield client


def submit(client,**fields):
    return client.post('/api/videos',files={k:(None,str(v))for k,v in {'concept':'물의 순환',**fields}.items()})


def completed(client,id):
    for _ in range(200):
        value=client.get('/api/videos/'+id).json()
        if value['status'] in {'completed','failed','cancelled'}:return value
        time.sleep(.01)
    raise AssertionError('job did not finish')


def test_api_202_ownership_cookie_and_range(client):
    response=submit(client);assert response.status_code==202
    id=response.json()['job_id'];assert response.headers['location']=='/api/videos/'+id
    cookie=response.headers['set-cookie'].lower();assert 'httponly' in cookie and 'samesite=strict' in cookie
    assert 'concept' not in response.json() and 'token' not in response.json()
    assert completed(client,id)['status']=='completed'
    path=f'/api/videos/{id}/file'
    part=client.get(path,headers={'Range':'bytes=2-8'})
    assert part.status_code==206 and part.content==MEDIA[2:9]
    assert part.headers['content-range']==f'bytes 2-8/{len(MEDIA)}'
    assert part.headers['cache-control']=='private, no-store'
    assert client.get(path,headers={'Range':'bytes=99999-'}).status_code==416
    assert 'attachment' in client.get(path+'?download=1').headers['content-disposition']
    token=client.cookies.get(COOKIE);client.cookies.clear()
    for method,url in [('get',f'/api/videos/{id}'),('get',path),('delete',f'/api/videos/{id}')]:
        assert getattr(client,method)(url).status_code==404
    client.cookies.set(COOKIE,'x'*43)
    assert client.get(path).status_code==404
    client.cookies.clear();client.cookies.set(COOKIE,token)
    assert client.delete('/api/videos/'+id).json()['status']=='cancelled'
    assert client.get(path).status_code==409


@pytest.mark.parametrize('fields',[{'concept':'','question':''},{'target_duration_seconds':29},{'student_level':'other'},{'format':'html'},{'command':'unsafe'}])
def test_video_multipart_validation(client,fields):
    assert submit(client,**fields).status_code==422


def test_consent_and_csrf_before_any_generation(client):
    from backend.app.config import get_settings
    main.app.dependency_overrides[get_settings]=lambda:Settings(mode='gemini',api_key='fixture-key')
    assert submit(client).status_code==428
    assert client.post('/api/videos',headers={'Origin':'https://foreign.invalid'},files={'concept':(None,'미분계수')}).status_code==403
    assert not main.app.state.video_jobs.jobs


def test_file_path_cannot_escape_store(client):
    response=submit(client);id=response.json()['job_id'];completed(client,id)
    assert client.get(f'/api/videos/{id}/file?path=/etc/passwd').content==MEDIA
    assert client.get('/api/videos/'+('f'*32)+'/file').status_code==404
    assert client.get('/api/videos/not-a-job').status_code==404
