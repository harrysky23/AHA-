"""Offline policies and failure cleanup. No Chrome, speech, or AI calls."""
import json
from pathlib import Path
import sys
import time

import pytest

from backend.app.providers.base import StoryboardInput
from backend.app.rendering import engine
from backend.app.rendering import tts
from backend.app.rendering.browser import template_html
from backend.app.rendering.core import Budget, RenderError, RenderOptions, run_process
from backend.app.rendering.engine import render_slot, render_storyboard, validate_spec
from backend.app.rendering.tts import fit_ratio
from backend.app.rendering.worker import verify_media
from backend.app.services.materials import MaterialContext
from backend.app.services.storyboard_mock import generate_mock_storyboard


def story():
    return generate_mock_storyboard(StoryboardInput('미분계수', '원리를 설명해 주세요.', MaterialContext()))


@pytest.fixture(autouse=True)
def isolated_render_lock(tmp_path,monkeypatch):
    monkeypatch.setattr(engine.tempfile,'gettempdir',lambda:str(tmp_path))


@pytest.mark.parametrize('kwargs', [{'fps':0}, {'fps':31}, {'fps':True}, {'preview':1},
    {'timeout_seconds':0}, {'timeout_seconds':1801}, {'max_disk_bytes':100}])
def test_runtime_options_bounded(kwargs):
    with pytest.raises(ValueError): RenderOptions(**kwargs)


def test_revalidate_mutated_spec_and_unknown_code():
    value=story();value.scenes[0].end_seconds=59.
    with pytest.raises(RenderError, match='StoryboardSpec'): validate_spec(value)
    value=story().model_dump();value['scenes'][0]['visualization']['javascript']='untrusted'
    with pytest.raises(RenderError) as error: validate_spec(value)
    assert error.value.code=='invalid_storyboard'


def test_busy_slot_fails_without_queue():
    with render_slot():
        with pytest.raises(RenderError) as error:
            with render_slot(): pass
        assert error.value.code=='render_busy'
    with render_slot(): pass


def test_disk_budget_and_deadline(tmp_path):
    budget=Budget(tmp_path,RenderOptions(max_disk_bytes=1024**2,min_free_bytes=0))
    (tmp_path/'too-large').write_bytes(b'x'*(1024**2+1))
    with pytest.raises(RenderError) as error: budget.check()
    assert error.value.code=='disk_limit'
    budget.deadline=time.monotonic()-1
    with pytest.raises(RenderError) as error: budget.check()
    assert error.value.code=='render_timeout'


def test_disk_reserve(tmp_path):
    budget=Budget(tmp_path,RenderOptions(min_free_bytes=10**20))
    with pytest.raises(RenderError) as error: budget.check()
    assert error.value.code=='disk_full'


def test_child_timeout_and_sanitized_failure(tmp_path,monkeypatch):
    budget=Budget(tmp_path,RenderOptions(min_free_bytes=0))
    budget.scene_id='scene_2';budget.deadline=time.monotonic()+.15
    with pytest.raises(RenderError) as error:
        run_process([sys.executable,'-c','import time; time.sleep(10)'],budget,'tts_failed')
    assert error.value.code=='render_timeout' and error.value.scene_id=='scene_2'
    budget.deadline=time.monotonic()+5
    with pytest.raises(RenderError) as error:
        run_process([sys.executable,'-c','import sys; print("private narration",file=sys.stderr); sys.exit(1)'],budget,'tts_failed')
    assert 'private narration' not in str(error.value) and error.value.code=='tts_failed'


@pytest.mark.parametrize('duration,length,expected',[(6,10,1),(10,10,10/9.85),(12,10,12/9.85)])
def test_speech_fits_without_truncation(duration,length,expected):
    assert fit_ratio(duration,length)==pytest.approx(expected)


@pytest.mark.parametrize('duration,length',[(14,10),(0,10),(3,.1),(float('nan'),10),(float('inf'),10)])
def test_long_or_invalid_speech_is_error(duration,length):
    with pytest.raises(RenderError): fit_ratio(duration,length)


def test_template_only_owned_script_and_no_remote_resources():
    html=template_html()
    assert "script-src 'sha256-" in html and "connect-src 'none'" in html
    assert 'https://' not in html and '<script src=' not in html
    assert 'eval(' not in html and 'new Function' not in html and 'innerHTML' not in html


def test_tts_uses_plain_stdin_without_speech_directives(tmp_path,monkeypatch):
    captured={}
    monkeypatch.setattr(tts.platform,'system',lambda:'Darwin')
    monkeypatch.setattr(tts,'executable',lambda name:name)
    def fake_process(command,budget,code,*,input_data):
        captured.update(command=command,spoken=input_data.decode())
        Path(command[-1]).write_bytes(b'x'*256)
    monkeypatch.setattr(tts,'run_process',fake_process)
    text='한국어 설명 [[rate 9999]] 을 명령으로 해석하지 않아요.'
    tts.MacOSSay().synthesize(text,tmp_path/'speech.aiff',Budget(tmp_path,RenderOptions()))
    assert text not in ' '.join(captured['command'])
    assert '[[' not in captured['spoken'] and '［［rate 9999］］' in captured['spoken']


def test_tts_non_macos_returns_actionable_error(tmp_path,monkeypatch):
    monkeypatch.setattr(tts.platform,'system',lambda:'Linux')
    with pytest.raises(RenderError) as error:
        tts.MacOSSay().synthesize('음성 생성 설명이에요.',tmp_path/'speech.aiff',Budget(tmp_path,RenderOptions()))
    assert error.value.code=='tts_unavailable'


def fake_worker(tmp_path,monkeypatch,body):
    # A real harmless child substitutes for Chrome/TTS. Exercises parent lifetime,
    # filesystem budget, environment stripping and cleanup rather than rendering.
    path=tmp_path/'fake-python'
    path.write_text(f'#!{sys.executable}\nimport os,sys,json,time\nfrom pathlib import Path\nw=Path(sys.argv[-1])\n'+body)
    path.chmod(0o700)
    monkeypatch.setattr(engine.sys,'executable',str(path))
    monkeypatch.setattr(engine,'executable',lambda name:name)


def test_failed_worker_cleanup_and_scene_diagnostic(tmp_path,monkeypatch):
    fake_worker(tmp_path,monkeypatch,"(w/'error.json').write_text(json.dumps({'code':'tts_failed','message':'로컬 음성 생성 실패','scene_id':'scene_3'}))\nsys.exit(1)\n")
    with pytest.raises(RenderError) as error: render_storyboard(story(),tmp_path/'out.mp4')
    assert error.value.code=='tts_failed' and error.value.scene_id=='scene_3'
    assert not list(tmp_path.glob('.aha-render-*')) and not (tmp_path/'out.mp4').exists()


def test_parent_disk_monitor_kills_child_and_cleans(tmp_path,monkeypatch):
    fake_worker(tmp_path,monkeypatch,"(w/'large').write_bytes(b'x'*2*1024**2)\ntime.sleep(20)\n")
    start=time.monotonic()
    with pytest.raises(RenderError) as error:
        render_storyboard(story(),tmp_path/'out.mp4',RenderOptions(max_disk_bytes=1024**2,min_free_bytes=0))
    assert error.value.code=='disk_limit' and time.monotonic()-start<5
    assert not list(tmp_path.glob('.aha-render-*'))


def test_parent_timeout_kills_child_and_cleans(tmp_path,monkeypatch):
    fake_worker(tmp_path,monkeypatch,"(w/'progress.json').write_text(json.dumps({'scene_id':'scene_1'}))\ntime.sleep(20)\n")
    original=engine.Budget
    def short_budget(root,options):
        b=original(root,options);b.deadline=time.monotonic()+1.2;return b
    monkeypatch.setattr(engine,'Budget',short_budget)
    with pytest.raises(RenderError) as error: render_storyboard(story(),tmp_path/'out.mp4')
    assert error.value.code=='render_timeout' and error.value.scene_id=='scene_1'
    assert not list(tmp_path.glob('.aha-render-*'))


def test_credentials_do_not_enter_worker_and_output_not_overwritten(tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-secret')
    fake_worker(tmp_path,monkeypatch,"assert 'GEMINI_API_KEY' not in os.environ\n(w/'result.mp4').write_bytes(b'fake media')\n(w/'report.json').write_text(json.dumps({'sanitized':True}))\n")
    output=tmp_path/'out.mp4'
    assert render_storyboard(story(),output)=={'sanitized':True}
    with pytest.raises(RenderError) as error: render_storyboard(story(),output)
    assert error.value.code=='output_exists' and output.read_bytes()==b'fake media'


def test_invalid_media_dimensions_duration_and_audio():
    value={'streams':[{'codec_type':'video','codec_name':'h264','width':540,'height':960,'pix_fmt':'yuv420p','duration':'45','avg_frame_rate':'3/1'},
        {'codec_type':'audio','codec_name':'aac','duration':'45','channels':1,'sample_rate':'48000'}], 'format':{'duration':'45'}}
    assert verify_media(value,story(),RenderOptions(preview=True,fps=3))['duration_seconds']==45
    for field,bad in [('codec_name','vp9'),('width',1920),('duration','44')]:
        altered=json.loads(json.dumps(value));altered['streams'][0][field]=bad
        with pytest.raises(RenderError): verify_media(altered,story(),RenderOptions(preview=True,fps=3))
    value['streams'].pop()
    with pytest.raises(RenderError): verify_media(value,story(),RenderOptions(preview=True,fps=3))
