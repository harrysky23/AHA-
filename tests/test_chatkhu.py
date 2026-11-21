"""HTTP doubles only. No real ChatKHU calls or user keys, even with configured .env."""
import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time
import wave
import zlib

import httpx
import pytest

from backend.app.config import ConfigurationError
from backend.app.providers.chatkhu import (Approval, ChatKHUError, ChatKHUSettings, GatewayClient,
    ChatKHUImageProvider, ChatKHUVideoProvider, ChatKHUTTSProvider)
from backend.app.providers.chatkhu.artifacts import validate_media, save_media
from backend.app.providers.chatkhu.client import accounting, operation_path
from backend.app.providers.chatkhu.contracts import fingerprint
from backend.app.providers.chatkhu.requests import image_request, video_request, tts_request
from scripts import check_chatkhu as cli

SETTINGS=ChatKHUSettings(api_key='fixture-private-chatkhu-key')
COST={'credits':34.,'bound':'minimum','source':'fixture-not-real-estimate'}


def png():
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0'+b'\x80\x50\xff'*2+b'\0'+b'\x80\x50\xff'*2))+chunk(b'IEND',b'')


def approve(kind,payload):return Approval(kind,fingerprint(kind,payload),True)


def inspection(path,kind):
    assert path.is_file()
    return {'unit_test_double':True,'kind':kind}


@pytest.mark.parametrize('field,value',[
    ('base_url','http://factchat-cloud.mindlogic.ai/v1/gateway'),('base_url','https://evil.invalid/v1/gateway'),
    ('base_url','https://key@factchat-cloud.mindlogic.ai/v1/gateway'),('base_url',SETTINGS.base_url+'?key=private'),
    ('image_model','not-documented'),('video_model','unapproved-model'),('tts_model','gemini-3.8-flash-tts')])
def test_configuration_fails_closed(field,value):
    with pytest.raises(ConfigurationError):replace(SETTINGS,**{field:value}).validate()
    assert SETTINGS.api_key not in repr(SETTINGS) and SETTINGS.api_key not in json.dumps(SETTINGS.public())


def test_image_request_response_and_single_call(tmp_path):
    calls=[];payload=image_request(SETTINGS)
    def handler(request):
        calls.append(request)
        assert request.url.path=='/v1/gateway/images/generate/'
        assert request.headers['authorization']=='Bearer '+SETTINGS.api_key
        assert json.loads(request.content)==payload
        return httpx.Response(200,json={'data':[{'url':'data:image/png;base64,'+base64.b64encode(png()).decode()}],
            'credits_charged':35.1234,'billing':{'deducted_credit':35.1234},'usage':{'total_tokens':100}})
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(handler)) as client:
        provider=ChatKHUImageProvider(client,inspect=inspection)
        artifact=provider.generate(payload,tmp_path/'image',approve('image',payload),COST)
        assert artifact.path.read_bytes()==png() and artifact.kind=='image'
        assert artifact.sha256==hashlib.sha256(png()).hexdigest()
        assert artifact.accounting[1]['credits_charged']==35.1234
        with pytest.raises(ChatKHUError) as error:
            provider.generate(payload,tmp_path/'another',approve('image',payload),COST)
        assert error.value.code=='call_limit' and len(calls)==1


@pytest.mark.parametrize('status',[400,401,402,403,404,429,500,503,504])
def test_http_errors_never_retry_or_leak_key(tmp_path,status):
    calls=[];payload=image_request(SETTINGS)
    def handler(request):
        calls.append(request)
        return httpx.Response(status,json={'detail':SETTINGS.api_key+' raw private prompt'})
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ChatKHUError) as error:
            ChatKHUImageProvider(client,inspect=inspection).generate(payload,tmp_path/'error',approve('image',payload),COST)
        assert error.value.status==status and len(calls)==1
        assert SETTINGS.api_key not in str(error.value) and 'raw private prompt' not in str(error.value)


def test_timeout_consumes_attempt_and_requires_dashboard_check(tmp_path):
    calls=[];payload=tts_request(SETTINGS)
    def handler(request):calls.append(request);raise httpx.ReadTimeout('fixture',request=request)
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(handler)) as client:
        provider=ChatKHUTTSProvider(client,inspect=inspection)
        with pytest.raises(ChatKHUError) as error:provider.generate(payload,tmp_path/'speech',approve('tts',payload),COST)
        assert error.value.code=='request_timeout'
        with pytest.raises(ChatKHUError) as error:provider.generate(payload,tmp_path/'again',approve('tts',payload),COST)
        assert error.value.code=='call_limit' and len(calls)==1


def test_approval_change_unknown_cost_and_overwrite_block_before_post(tmp_path):
    calls=[];payload=image_request(SETTINGS)
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(lambda r:calls.append(r))) as client:
        provider=ChatKHUImageProvider(client,inspect=inspection)
        with pytest.raises(ChatKHUError) as error:provider.generate(payload,tmp_path/'x',Approval('image','0'*64,True),COST)
        assert error.value.code=='approval_mismatch'
        with pytest.raises(ChatKHUError) as error:provider.generate(payload,tmp_path/'x',Approval('image',fingerprint('image',payload)),COST)
        assert error.value.code=='cost_confirmation_required'
        (tmp_path/'x.png').write_bytes(png())
        with pytest.raises(ChatKHUError) as error:provider.generate(payload,tmp_path/'x',approve('image',payload),COST)
        assert error.value.code=='output_exists' and not calls


def test_documented_video_parameters_and_data_reference(tmp_path):
    image=tmp_path/'source.png';image.write_bytes(png())
    kling=video_request(SETTINGS,image)
    assert kling['parameters']=={'duration':3,'mode':'standard','generate_audio':False,'aspect_ratio':'9:16'}
    assert kling['input_urls'][0].startswith('data:image/png;base64,')
    seed=video_request(replace(SETTINGS,video_model='bytedance/seedance-2.0'),image)
    assert seed['parameters']=={'duration':5,'resolution':'720p','aspect_ratio':'9:16'}
    with pytest.raises(ChatKHUError):video_request(SETTINGS)
    assert 'input_urls' not in video_request(SETTINGS,text_only=True)


def test_video_poll_download_no_credentials_to_cdn(tmp_path):
    payload=video_request(SETTINGS,text_only=True);operation='gw.fixture.fal-ai/kling-video/v3::id'
    calls=[];cdn=[]
    def handler(request):
        calls.append(request)
        if request.method=='POST':return httpx.Response(200,json={'operation_id':operation,'status':'processing','credits_charged':100.25})
        assert request.url.params['model']==SETTINGS.video_model
        assert request.url.path=='/v1/gateway'+operation_path('video',operation)
        return httpx.Response(200,json={'operation_id':operation,'status':'completed','video_uri':'https://v3b.fal.media/files/fixture.mp4'})
    raw=b'\x00\x00\x00\x18ftyp'+b'fixture-MP4-not-real'
    def media(request):cdn.append(request);assert 'authorization' not in request.headers;return httpx.Response(200,content=raw)
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(handler),media_transport=httpx.MockTransport(media),sleep=lambda _:None) as client:
        artifact=ChatKHUVideoProvider(client,inspect=inspection).generate(payload,tmp_path/'movie',approve('video',payload),COST)
        assert artifact.path.read_bytes()==raw and len(calls)==2 and len(cdn)==1
        assert artifact.accounting[1]['credits_charged']==100.25


def test_gateway_download_constructed_from_operation_not_arbitrary_uri(tmp_path):
    calls=[];payload=video_request(SETTINGS,text_only=True);operation='gw.fixture.id'
    def handler(request):
        calls.append(request)
        if request.method=='POST':return httpx.Response(200,json={'operation_id':operation,'status':'processing'})
        if request.url.path.endswith('/download/'):
            return httpx.Response(200,content=b'\0\0\0\x18ftypfixture')
        return httpx.Response(200,json={'status':'completed','video_uri':'/v1/gateway'+operation_path('video',operation)+'download/?model=ignored'})
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(handler),sleep=lambda _:None) as client:
        artifact=ChatKHUVideoProvider(client,inspect=inspection).generate(payload,tmp_path/'v',approve('video',payload),COST)
        assert artifact.path.exists() and len(calls)==3 and calls[-1].url.params['model']==SETTINGS.video_model


def test_tts_pcm_to_wav_and_official_billing_headers(tmp_path):
    payload=tts_request(SETTINGS);raw=b'\x00\x01'*24000
    assert set(payload)=={'model','input','voice'} and 'instructions' not in payload
    def handler(request):
        assert request.url.path=='/v1/gateway/audio/speech/'
        return httpx.Response(200,content=raw,headers={'Content-Type':'audio/pcm','X-Input-Tokens':'100',
            'X-Output-Tokens':'800','X-Billing':json.dumps({'deducted_credit':16.1,'cost_usd':.04})})
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(handler)) as client:
        artifact=ChatKHUTTSProvider(client,inspect=inspection).generate(payload,tmp_path/'speech',approve('tts',payload),COST)
        with wave.open(str(artifact.path),'rb') as w:
            assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,24000)
            assert w.readframes(w.getnframes())==raw
        assert artifact.accounting[1]['billing']['deducted_credit']==16.1
        assert artifact.accounting[1]['input_tokens']==100 and artifact.accounting[1]['output_tokens']==800


def test_missing_usage_is_unknown_not_zero():
    data=accounting();assert data['credits_charged'] is None and data['billing'] is None
    assert accounting({'credits_charged':True})['credits_charged'] is None
    assert accounting({'credits_charged':0})['credits_charged']==0


@pytest.mark.parametrize('operation',['../credits','a/../models','https://evil.invalid/','a?key=x','a#b','a%2fb','/leading'])
def test_operation_path_does_not_allow_injection(operation):
    with pytest.raises(ChatKHUError):operation_path('video',operation)


@pytest.mark.parametrize('url',['http://v3b.fal.media/f.mp4','https://localhost/f.mp4','https://169.254.169.254/','https://fal.media.evil.invalid/f.mp4','https://user:secret@v3b.fal.media/f.mp4'])
def test_untrusted_downloads_never_request(url):
    calls=[]
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(lambda r:calls.append(r)),media_transport=httpx.MockTransport(lambda r:calls.append(r))) as client:
        with pytest.raises(ChatKHUError):client.download('image',SETTINGS.image_model,url)
        assert not calls


def test_poll_timeout_persists_operation_and_resume_is_get_only(tmp_path):
    operation='gw.pending.model/id';calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,json={'status':'processing','operation_id':operation})
    with GatewayClient(replace(SETTINGS,max_polls=2),transport=httpx.MockTransport(handler),sleep=lambda _:None) as client:
        with pytest.raises(ChatKHUError) as error:ChatKHUVideoProvider(client,inspect=inspection).resume(operation,tmp_path/'late')
        assert error.value.code=='operation_timeout' and error.value.operation_id==operation
        assert len(calls)==2 and all(r.method=='GET' for r in calls)
        assert client.events[0]['phase']=='operation' and client.sent['video']==0


def test_preflight_quote_is_separate_from_generation():
    calls=[];payload=image_request(SETTINGS)
    def handler(request):
        calls.append(request)
        if request.method=='GET':return httpx.Response(200,json={'data':[{'id':SETTINGS.image_model,'type':'image'}]})
        sent=json.loads(request.content);assert sent['kind']=='image' and 'prompt' not in sent
        return httpx.Response(200,json={'object':'estimate','kind':'image','model':SETTINGS.image_model,'credits':34,'bound':'minimum','exact':False})
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(handler)) as client:
        assert client.models()['data'][0]['id']==SETTINGS.image_model
        assert client.estimate('image',payload)['bound']=='minimum'
        with pytest.raises(ChatKHUError):client.estimate('tts',tts_request(SETTINGS))
        assert len(calls)==2 and all(count==0 for count in client.sent.values())


@pytest.mark.parametrize('body',[{'data':[{'url':'data:image/png;base64,broken%%'}]},{'data':[]},{'status':'unknown'}])
def test_invalid_responses_do_not_publish_media(tmp_path,body):
    payload=image_request(SETTINGS)
    with GatewayClient(SETTINGS,transport=httpx.MockTransport(lambda _:httpx.Response(200,json=body))) as client:
        with pytest.raises(ChatKHUError):ChatKHUImageProvider(client,inspect=inspection).generate(payload,tmp_path/'bad',approve('image',payload),COST)
        assert not list(tmp_path.iterdir())


def test_invalid_decode_does_not_leave_untrusted_asset(tmp_path):
    def reject(*_):raise ChatKHUError('invalid_media','fixture decoder rejection')
    with pytest.raises(ChatKHUError):save_media(png(),'image',tmp_path/'bad',reject)
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(not shutil.which('ffprobe') or not shutil.which('ffmpeg'),reason='local optional decoder dependency')
def test_real_local_decoder_on_synthetic_fixture_only(tmp_path):
    path,metadata=save_media(png(),'image',tmp_path/'fixture')
    assert metadata['width']==2 and metadata['height']==2
    speech,audio=save_media(b'\x00\x01'*24000,'tts',tmp_path/'speech')
    assert audio['duration_seconds']==pytest.approx(1.)


def test_cli_default_and_missing_approval_never_build_client(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(cli,'ROOT',tmp_path)
    monkeypatch.setattr(cli,'get_chatkhu_settings',lambda:SETTINGS)
    def forbidden(*a,**kw):raise AssertionError('No network client before approval')
    monkeypatch.setattr(cli,'GatewayClient',forbidden)
    assert cli.main(['--kind','image'])==0
    assert cli.main(['--kind','tts'])==0
    assert cli.main(['--kind','video'])==0
    assert cli.main(['--kind','image','--live'])==1
    captured=capsys.readouterr();assert SETTINGS.api_key not in captured.out+captured.err
    assert 'approval_required' in captured.err


def test_quote_must_match_payload_and_be_fresh(tmp_path):
    path=tmp_path/'quote.json'
    path.write_text(json.dumps({'request_hash':'a'*64,'action':'preflight','checked_at':time.time(),'cost':COST}))
    assert cli.load_quote(path,'a'*64)==COST
    with pytest.raises(ChatKHUError):cli.load_quote(path,'b'*64)
    path.write_text(json.dumps({'request_hash':'a'*64,'action':'preflight','checked_at':0,'cost':COST}))
    with pytest.raises(ChatKHUError):cli.load_quote(path,'a'*64)
