import asyncio
from copy import deepcopy
import json

import httpx
from fastapi.testclient import TestClient
import pytest

from backend.app.config import ConfigurationError, Settings, get_settings
from backend.app.main import app
from backend.app.providers.gemini import GeminiProvider, MAX_RESPONSE_BYTES
from backend.app.providers.base import GenerationInput
from backend.app.services.validation import parse_spec
from backend.app.services.errors import LearningError
from backend.app.services.materials import MaterialContext, analyze_material
from backend.app.services.mock import generate_mock
from backend.app.services.prompts import build_messages
from backend.app.services import lessons, materials
from pdf_fixture import pdf_bytes

client = TestClient(app)
CONTEXT = MaterialContext()
SETTINGS = Settings(mode='gemini',api_key='fixture-secret-never-log',model='gemini-2.5-flash-lite')


def spec_dict(context=CONTEXT):
    return generate_mock('미분계수','할선은 무엇인가요?',context).model_dump()


def envelope(spec=None):
    return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(spec if spec is not None else spec_dict(),ensure_ascii=False)}]}}],
            'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':20,'totalTokenCount':30}}


def call_provider(handler, context=CONTEXT):
    provider=GeminiProvider(SETTINGS,transport=httpx.MockTransport(handler))
    result=asyncio.run(provider.generate(GenerationInput('미분계수','할선은 무엇인가요?',context),'test-request'))
    return result.spec, {'provider':'gemini','usage':result.usage}


def test_mock_preserves_fixed_phase1_example_for_any_question():
    def learn(question):
        return client.post('/api/learn',files={'question':(None,question),'format':(None,'html')}).json()
    a,b=learn('h=0을 바로 대입하면 왜 안 되나요?'),learn('음수 h에서도 접선으로 가나요?')
    assert a['mode'] == b['mode'] == 'mock'
    assert a['lesson']['spec']['explanation'] == b['lesson']['spec']['explanation']
    assert a['lesson']['spec']['visualization']['variable']['initial'] == 1.2
    assert b['lesson']['spec']['visualization']['variable']['initial'] == 1.2
    assert a['generation']['external_ai'] is False
    assert a['lesson']['spec']['analysis']['learning_level'] == b['lesson']['spec']['analysis']['learning_level']


def test_pdf_extraction_quotes_and_truncation():
    text='A calculus textbook says: the secant slope is 2+h.'
    context=asyncio.run(analyze_material(pdf_bytes(text),'application/pdf'))
    assert context.status == 'text_extracted'
    assert text in context.pages[0]['text']
    assert context.extracted_characters == len(text)
    response=client.post('/api/learn',data={'question':'미분계수','format':'html'},files={'file':('book.pdf',pdf_bytes(text),'application/pdf')})
    assert response.status_code == 200
    spec=response.json()['lesson']['spec']
    assert spec['source_quotes'] == [{'page':1,'quote':text}]
    truncated=asyncio.run(analyze_material(pdf_bytes('a'*13000),'application/pdf'))
    assert truncated.truncated and truncated.extracted_characters == 12000
    assert '12,000' in truncated.message


def test_korean_text_from_existing_reference_page():
    from io import BytesIO
    from pathlib import Path
    from pypdf import PdfReader, PdfWriter
    # Read an existing Korean text layer, removing images in memory to fit 5 MiB.
    source=next(Path('references').glob('*.pdf'))
    writer=PdfWriter();writer.add_page(PdfReader(source).pages[6]);writer.remove_images()
    memory=BytesIO();writer.write(memory)
    context=asyncio.run(analyze_material(memory.getvalue(),'application/pdf'))
    assert context.status == 'text_extracted'
    assert '학습' in context.pages[0]['text']


@pytest.mark.parametrize('data,code',[(b'%PDF-not-a-pdf','invalid_pdf'),(pdf_bytes(encrypted=True),'encrypted_pdf'),(pdf_bytes(pages=21),'pdf_page_limit')])
def test_pdf_rejections(data,code):
    with pytest.raises(LearningError) as error:
        asyncio.run(analyze_material(data,'application/pdf'))
    assert error.value.code == code
    assert error.value.fallback


def test_scanned_or_blank_pdf_and_image_do_not_invent_text():
    context=asyncio.run(analyze_material(pdf_bytes(text=None),'application/pdf'))
    assert context.status == 'no_extractable_text' and context.pages == []
    assert context.empty_pages == [1]
    assert 'OCR' in context.message
    image=asyncio.run(analyze_material(b'image','image/png'))
    assert image.status == 'image_unsupported' and image.pages == []


def test_pdf_timeout_kills_child(monkeypatch):
    class Process:
        returncode=None
        killed=False
        async def communicate(self,data=None):
            if not self.killed:
                raise TimeoutError
            return b'',b''
        def kill(self):
            self.killed=True
            self.returncode=-9
    process=Process()
    async def launch(*args,**kwargs):return process
    monkeypatch.setattr(materials.asyncio,'create_subprocess_exec',launch)
    with pytest.raises(LearningError) as error:
        asyncio.run(analyze_material(b'%PDF-','application/pdf'))
    assert error.value.code == 'pdf_timeout'
    assert process.killed


def test_documented_request_with_fake_transport_and_no_secret_in_result():
    seen=[]
    def handle(request):
        seen.append(request)
        return httpx.Response(200,json=envelope())
    spec, metadata=call_provider(handle)
    payload=json.loads(seen[0].content)
    assert seen[0].headers['x-goog-api-key'] == SETTINGS.api_key
    assert seen[0].url == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent'
    assert SETTINGS.api_key not in str(seen[0].url)
    assert payload['generationConfig']['maxOutputTokens'] == 4096
    assert payload['generationConfig']['responseMimeType'] == 'application/json'
    assert payload['generationConfig']['responseJsonSchema']['type'] == 'object'
    assert 'tools' not in payload
    assert 'JSON schema' in payload['systemInstruction']['parts'][0]['text']
    assert spec.visualization.type == 'secant_tangent_x2'
    assert metadata['provider'] == 'gemini' and metadata['usage']['totalTokenCount'] == 30
    assert SETTINGS.api_key not in repr(SETTINGS) + json.dumps(metadata)


def test_extracted_material_and_question_reach_prompt():
    context=MaterialContext(status='text_extracted',pages=[{'page':2,'text':'The slope is 2+h.'}],page_count=2)
    seen=[]
    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json=envelope(spec_dict(context)))
    call_provider(handle,context)
    user=json.loads(seen[0]['contents'][0]['parts'][0]['text'])
    assert user['pages'] == context.pages and user['question'] == '할선은 무엇인가요?'
    assert '신뢰하지 않는' in build_messages('','',context)[0]['content']


@pytest.mark.parametrize('status,code',[(401,'gemini_auth'),(403,'gemini_auth'),(429,'gemini_quota_exceeded'),(500,'gemini_unavailable'),(302,'gemini_unavailable')])
def test_provider_http_errors_do_not_leak_or_retry(status,code):
    seen=[]
    def handle(request):
        seen.append(request)
        return httpx.Response(status,text='secret upstream payload '+SETTINGS.api_key)
    with pytest.raises(LearningError) as error:call_provider(handle)
    assert error.value.code == code and error.value.fallback
    assert SETTINGS.api_key not in str(error.value)
    assert len(seen) == 1


def test_provider_timeout():
    def handle(request):raise httpx.ReadTimeout('never show this secret')
    with pytest.raises(LearningError) as error:call_provider(handle)
    assert error.value.code == 'gemini_timeout' and error.value.status == 504


@pytest.mark.parametrize('body',[
    {}, {'candidates':[]}, {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':{'not':'text'}}]}}]},
    {'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{'name':'execute'}}]}}]},
])
def test_bad_envelope(body):
    with pytest.raises(LearningError) as error:
        call_provider(lambda request:httpx.Response(200,json=body))
    assert error.value.code == 'gemini_invalid_response'


def test_response_size_limit():
    with pytest.raises(LearningError) as error:
        call_provider(lambda request:httpx.Response(200,content=b'x'*(MAX_RESPONSE_BYTES+1)))
    assert error.value.code == 'gemini_response_limit'


@pytest.mark.parametrize('mutate',[
    lambda s:s.update(javascript='alert(1)'),
    lambda s:s['visualization'].update(type='arbitrary_html'),
    lambda s:s['visualization'].update(a=2),
    lambda s:s['visualization']['variable'].update(initial=50),
    lambda s:s['visualization']['variable'].update(initial=.12345),
    lambda s:s['quiz'][0].update(h=.00001,answer=2.00001),
    lambda s:s['examples'][0].update(secant_slope=99),
    lambda s:s['quiz'][0].update(answer=99),
    lambda s:s['quiz'][1].update(answer=0),
    lambda s:s['source_quotes'].append({'page':1,'quote':'invented text'}),
])
def test_invalid_spec_math_code_or_citation(mutate):
    data=deepcopy(spec_dict());mutate(data)
    with pytest.raises(LearningError) as error:parse_spec(json.dumps(data),CONTEXT)
    assert error.value.code == 'invalid_lesson_spec'


def test_json_fences_duplicates_and_nonfinite_are_rejected():
    for content in ['```json\n{}\n```','{"schema_version":"1","schema_version":"1"}','{"x":NaN}']:
        with pytest.raises(LearningError):parse_spec(content,CONTEXT)


def test_citation_must_match_the_correct_page():
    context=MaterialContext(pages=[{'page':2,'text':'An exact sentence.'}])
    data=spec_dict(context)
    parse_spec(json.dumps(data),context)
    for quotes in [[],[{'page':1,'quote':'An exact sentence.'}],[{'page':2,'quote':'A fake sentence.'}]]:
        data['source_quotes']=quotes
        with pytest.raises(LearningError):parse_spec(json.dumps(data),context)


def test_consent_required_no_upstream_call_and_key_never_served():
    app.dependency_overrides[get_settings]=lambda:SETTINGS
    response=client.post('/api/learn',files={'question':(None,'미분'),'format':(None,'html')})
    assert response.status_code == 428 and response.json()['code'] == 'consent_required'
    health=client.get('/api/health').json()
    assert health['mode'] == 'gemini' and health['ai_configured'] is True
    assert SETTINGS.api_key not in json.dumps(health)
    assert client.get('/.env').status_code == 404
    assert client.get('/static/../.env').status_code == 404
    video=client.post('/api/learn',files={'question':(None,'미분'),'format':(None,'shorts')})
    assert video.status_code == 200 and video.json()['mode'] == 'local_demo'


def test_gemini_route_with_transport_fixture_not_real_api(monkeypatch):
    app.dependency_overrides[get_settings]=lambda:SETTINGS
    class Provider(GeminiProvider):
        async def generate(self,request,request_id):
            self.transport=httpx.MockTransport(lambda http_request:httpx.Response(200,json=envelope(spec_dict(request.material))))
            return await super().generate(request,request_id)
    monkeypatch.setattr(lessons,'get_provider',lambda settings:Provider(settings))
    response=client.post('/api/learn',data={'question':'미분','format':'html','consent':'true'},files={'file':('book.pdf',pdf_bytes(),'application/pdf')})
    data=response.json()
    assert response.status_code == 200 and data['mode'] == 'gemini'
    assert data['generation']['external_ai'] is True
    assert data['material']['analyzed'] is True
    assert data['verification']['numeric_checks'] == 'passed'
    assert SETTINGS.api_key not in response.text


def test_missing_settings_and_unsupported_scope():
    app.dependency_overrides[get_settings]=lambda:Settings(mode='gemini')
    response=client.post('/api/learn',files={'question':(None,'미분'),'format':(None,'html'),'consent':(None,'true')})
    assert response.status_code == 503 and response.json()['fallback_available']
    app.dependency_overrides[get_settings]=lambda:Settings()
    response=client.post('/api/learn',files={'question':(None,'수요 공급'),'format':(None,'html')})
    assert response.status_code == 200 and response.json()['mode'] == 'mock'


@pytest.mark.parametrize('model',['http://evil.test','../gemini-model','models/gemini-2.5-flash-lite','gemini-model?key=secret',''])
def test_model_cannot_change_endpoint_or_add_credentials(model):
    from dataclasses import replace
    with pytest.raises(ConfigurationError):replace(SETTINGS,model=model).validate_gemini()
