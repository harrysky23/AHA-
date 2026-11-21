import asyncio
from dataclasses import replace
import json

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app.config import Settings, ConfigurationError, get_settings
from backend.app.main import app
from backend.app.providers.base import GenerationInput, ProviderResult
from backend.app.providers.elice import EliceProvider
from backend.app.providers.gemini import GeminiProvider, response_schema
from backend.app.schemas import LessonSpec
from backend.app.services.cache import LessonCache
from backend.app.services.errors import LearningError
from backend.app.services.materials import MaterialContext
from backend.app.services.mock import generate_mock
from backend.app.services import lessons, prompts
from pdf_fixture import pdf_bytes

S=Settings(mode='gemini',api_key='private-test-key-not-real')
REQUEST=GenerationInput('미분계수','h=0은요?',MaterialContext())


def result():
    return ProviderResult(generate_mock('','',MaterialContext()),'test-model',{'totalTokenCount':30})


def test_cache_ttl_lru_copy_and_disabled_mode():
    async def run():
        now=[10]
        cache=LessonCache(clock=lambda:now[0]); calls=[]
        async def factory():calls.append(1);return result()
        first,status=await cache.get_or_create('a',factory,10,2)
        assert status=='miss'
        first.spec.title='mutation'
        second,status=await cache.get_or_create('a',factory,10,2)
        assert status=='hit' and second.spec.title!='mutation' and len(calls)==1
        await cache.get_or_create('b',factory,10,2)
        await cache.get_or_create('a',factory,10,2)
        await cache.get_or_create('c',factory,10,2)
        assert list(cache.entries)==['a','c']
        now[0]=21
        await cache.get_or_create('a',factory,10,2)
        assert len(calls)==4
        assert (await cache.get_or_create('a',factory,0,2))[1]=='disabled'
        assert len(calls)==5
        assert not cache.entries
    asyncio.run(run())


def test_identical_concurrent_requests_share_one_generation():
    async def run():
        cache=LessonCache();calls=[]
        async def factory():
            calls.append(1);await asyncio.sleep(.01);return result()
        results=await asyncio.gather(*(cache.get_or_create('same',factory,300,64) for _ in range(6)))
        assert len(calls)==1
        assert [status for value,status in results].count('miss')==1
        assert cache.pending=={}
    asyncio.run(run())


def test_cancelled_waiter_does_not_cancel_owner():
    async def run():
        cache=LessonCache();gate=asyncio.Event();started=asyncio.Event()
        async def factory():started.set();await gate.wait();return result()
        owner=asyncio.create_task(cache.get_or_create('key',factory,300,64))
        await started.wait()
        waiter=asyncio.create_task(cache.get_or_create('key',factory,300,64))
        await asyncio.sleep(0);waiter.cancel()
        with pytest.raises(asyncio.CancelledError):await waiter
        gate.set()
        assert (await owner)[1]=='miss'
        assert 'key' in cache.entries
    asyncio.run(run())


def test_errors_and_validation_failures_are_not_cached():
    async def run():
        cache=LessonCache();calls=[]
        async def factory():calls.append(1);raise LearningError('invalid_lesson_spec','test')
        for _ in range(2):
            with pytest.raises(LearningError):await cache.get_or_create('key',factory,300,64)
        assert len(calls)==2 and not cache.entries and not cache.pending
    asyncio.run(run())


def test_key_accounts_for_provider_model_prompt_schema_generation_and_private_input(monkeypatch):
    cache=LessonCache()
    base=cache.key('gemini',S.model,S,REQUEST)
    keys={base,cache.key('mock',S.model,S,REQUEST),cache.key('gemini','gemini-different',S,REQUEST),
          cache.key('gemini',S.model,replace(S,api_key='other-key'),REQUEST),
          cache.key('gemini',S.model,replace(S,max_output_tokens=2048),REQUEST),
          cache.key('gemini',S.model,S,GenerationInput('미분계수','different private question',MaterialContext())),
          cache.key('gemini',S.model,S,GenerationInput('미분계수',REQUEST.question,MaterialContext(status='text_extracted',pages=[{'page':1,'text':'Private PDF text'}])))}
    assert len(keys)==7 and all(len(key)==64 for key in keys)
    monkeypatch.setattr(prompts,'PROMPT_VERSION','changed')
    assert cache.key('gemini',S.model,S,REQUEST) not in keys
    monkeypatch.setattr(prompts,'PROMPT_VERSION','secant-ko-v3')
    original=LessonSpec.model_json_schema
    monkeypatch.setattr(LessonSpec,'model_json_schema',classmethod(lambda cls:{**original(),'description':'schema revision'}))
    assert cache.key('gemini',S.model,S,REQUEST)!=base
    assert REQUEST.question not in base and S.api_key not in base


def test_response_cache_reuses_only_spec_not_previous_filename_or_usage(monkeypatch):
    app.dependency_overrides[get_settings]=lambda:S
    calls=[]
    class Provider:
        name='gemini';model=S.model
        async def generate(self,request,request_id):
            calls.append(1)
            return ProviderResult(generate_mock('','',request.material),self.model,{'totalTokenCount':30})
    monkeypatch.setattr(lessons,'get_provider',lambda settings:Provider())
    client=TestClient(app)
    def post(name):return client.post('/api/learn',data={'question':'미분계수','format':'html','consent':'true'},files={'file':(name,pdf_bytes(),'application/pdf')})
    a,b=post('private-A.pdf').json(),post('private-B.pdf').json()
    assert len(calls)==1
    assert a['generation']['cached'] is False and b['generation']['cached'] is True
    assert a['generation']['usage'] and b['generation']['usage']=={}
    assert b['material']['filename']=='private-B.pdf' and b['material']['sent_to_provider'] is False
    assert a['generation']['request_id']!=b['generation']['request_id']
    assert 'private-A.pdf' not in json.dumps(b)


def test_elice_never_instantiates_http_client(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Elice must not open a client')
    monkeypatch.setattr(httpx,'AsyncClient',forbidden)
    with pytest.raises(LearningError) as error:
        asyncio.run(EliceProvider(Settings(mode='elice')).generate(REQUEST,'id'))
    assert error.value.code=='elice_not_implemented'


@pytest.mark.parametrize('status,body,code',[
    (400,{'error':{'status':'FAILED_PRECONDITION'}},'gemini_free_tier_unavailable'),
    (400,{'error':{'status':'INVALID_ARGUMENT'}},'gemini_request_invalid'),
    (400,{'error':{'details':[{'reason':'API_KEY_INVALID'}]}},'gemini_auth'),
    (404,{},'gemini_model_unavailable'),(504,{},'gemini_timeout'),
    (503,{'error':{'message':'This model is currently experiencing high demand.'}},'gemini_overloaded'),
])
def test_precise_gemini_failures(status,body,code):
    provider=GeminiProvider(S,transport=httpx.MockTransport(lambda req:httpx.Response(status,json=body)))
    with pytest.raises(LearningError) as error:asyncio.run(provider.generate(REQUEST,'id'))
    assert error.value.code==code


def test_429_retry_after_is_bounded_and_no_upstream_message_leaks():
    calls=[]
    def handle(request):
        calls.append(1)
        return httpx.Response(429,headers={'Retry-After':'17'},json={'error':{'message':'private echoed prompt '+S.api_key}})
    provider=GeminiProvider(S,transport=httpx.MockTransport(handle))
    with pytest.raises(LearningError) as error:asyncio.run(provider.generate(REQUEST,'id'))
    assert error.value.retry_after==17 and error.value.code=='gemini_quota_exceeded'
    assert S.api_key not in str(error.value) and len(calls)==1
    assert error.value.upstream_status==429 and S.api_key not in error.value.upstream_message


@pytest.mark.parametrize('reason,code',[('MAX_TOKENS','gemini_output_truncated'),('SAFETY','gemini_blocked'),('RECITATION','gemini_blocked')])
def test_non_success_finish_reason(reason,code):
    body={'candidates':[{'finishReason':reason}]}
    provider=GeminiProvider(S,transport=httpx.MockTransport(lambda req:httpx.Response(200,json=body)))
    with pytest.raises(LearningError) as error:asyncio.run(provider.generate(REQUEST,'id'))
    assert error.value.code==code


def test_native_schema_subset_and_local_math_constraints():
    schema=response_schema()
    text=json.dumps(schema)
    assert '$ref' not in text and 'multipleOf' not in text and 'const' not in text
    assert schema['properties']['visualization']['properties']['type']['enum']==['secant_tangent_x2']
    assert schema['properties']['quiz']['items']['properties']['answer']['type']==['number','null']


def test_config_alias_and_private_key(monkeypatch):
    from backend.app import config
    for key in ['AHA_AI_PROVIDER','AHA_AI_MODE','GEMINI_API_KEY']:
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setattr(config,'dotenv_values',lambda path:{'AHA_AI_MODE':'mock'})
    assert get_settings().mode=='mock'
    monkeypatch.setattr(config,'dotenv_values',lambda path:{'AHA_AI_PROVIDER':'gemini','GEMINI_API_KEY':'sensitive'})
    settings=get_settings()
    assert settings.mode=='gemini' and settings.model=='gemini-3.5-flash-lite'
    assert 'sensitive' not in repr(settings)
    monkeypatch.setenv('AHA_AI_MODE','elice')
    with pytest.raises(ConfigurationError):get_settings()
