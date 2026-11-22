import base64
import hashlib
from pathlib import Path
import re

from fastapi.testclient import TestClient
import pytest

from backend.app.main import MAX_BODY_BYTES, app
from backend.app.routes.learn import MAX_FILE_BYTES
from pdf_fixture import pdf_bytes

client = TestClient(app)
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')


def learn(**fields):
    # Always multipart, even for a question without an upload.
    return client.post('/api/learn', files={k: (None, v) for k, v in fields.items()})


def test_health_and_reference_preservation():
    health = client.get('/api/health').json()
    assert health['mode'] == 'mock' and health['external_ai'] is False
    reference = next(Path('references').glob('*.html'))
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == '63cccf869c0c75aedffc12fbe00cc7fb7c5be30210372c076f97261167f0e2b1'
    index = client.get('/')
    assert index.status_code == 200
    assert 'econSvg' in index.text and 'learn-form' in index.text
    for video in ['derivative', 'supply-demand']:
        result = client.get(f'/static/media/{video}-explainer.mp4', headers={'Range':'bytes=0-31'})
        assert result.status_code == 206
        assert b'ftyp' in result.content


def test_landing_revalidates_and_loads_current_workflow_script():
    page = client.get('/')
    assert page.headers['cache-control'] == 'no-cache'
    assert 'id="image-consent"' in page.text
    script = client.get('/static/workflow.js')
    version = hashlib.sha256(script.content).hexdigest()[:12]
    assert f'src="/static/workflow.js?v={version}"' in page.text


def test_deterministic_html_and_isolated_viewer():
    response = learn(concept='미분계수', question='왜 2인가요?', format='html')
    assert response.status_code == 200
    data = response.json()
    assert data['grounding']['status'] == 'no_material'
    assert data['lesson']['tangent_slope'] == 2
    assert data['video'] is None
    assert data['lesson']['spec'] == learn(concept='미분계수', question='왜 2인가요?', format='html').json()['lesson']['spec']
    lesson = client.get(data['lesson']['viewer_url'])
    policy = lesson.headers['Content-Security-Policy']
    assert "sandbox allow-scripts" in policy
    assert 'allow-same-origin' not in policy
    assert "connect-src 'none'" in policy
    for script in re.findall(r'<script>(.*?)</script>',lesson.text,re.S):
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        assert f"'sha256-{digest}'" in policy


@pytest.mark.parametrize('filename,mime,content', [
    ('필기.png','image/png',PNG), ('교재.pdf','application/pdf',pdf_bytes()),
    ('사진.jpg','image/jpeg',b'\xff\xd8\xff\xe0'), ('사진.webp','image/webp',b'RIFF\x00\x00\x00\x00WEBP'),
])
def test_upload_is_acknowledged_but_not_analyzed(filename,mime,content):
    response = client.post('/api/learn', data={'concept':'미분계수','format':'html'}, files={'file':(filename,content,mime)})
    assert response.status_code == 200
    material = response.json()['material']
    assert material['filename'] == filename and material['size_bytes'] == len(content) and material['analyzed'] is False
    assert response.json()['grounding']['status'] == ('text_extracted' if mime == 'application/pdf' else 'image_unsupported')


def test_shorts_is_explicitly_an_existing_sample():
    data = learn(question='미분을 설명해 줘',format='shorts').json()
    assert data['lesson'] is None
    assert data['video']['generated'] is False
    assert '9:16' in data['video']['notice']


@pytest.mark.parametrize('fields', [
    {'concept':'  ','question':'\n','format':'html'},
    {'question':'미분','format':'arbitrary'},
    {'concept':'a'*201,'format':'html'},
    {'question':'a'*2001,'format':'html'},
    {'question':'미분'},
])
def test_invalid_fields(fields):
    assert learn(**fields).status_code == 422


@pytest.mark.parametrize('filename,mime,content,status', [
    ('a.html','text/html',b'<script>alert(1)</script>',415),
    ('fake.pdf','application/pdf',b'not a pdf',415),
    ('a.pdf','image/png',PNG,415),
    ('empty.pdf','application/pdf',b'',415),
    ('huge.pdf','application/pdf',b'%PDF-'+b'x'*MAX_FILE_BYTES,413),
])
def test_reject_bad_upload(filename,mime,content,status):
    response = client.post('/api/learn', data={'question':'미분','format':'html'}, files={'file':(filename,content,mime)})
    assert response.status_code == status


def test_body_limit_without_content_length():
    async def run():
        events = []
        async def receive():
            return {'type':'http.request','body': b'x'*(MAX_BODY_BYTES+1),'more_body':False}
        async def send(event):
            events.append(event)
        scope = {'type':'http','method':'POST','path':'/api/learn','headers':[], 'query_string':b''}
        await app(scope, receive, send)
        assert events[0]['status'] == 413
    import asyncio
    asyncio.run(run())


def test_reject_multiple_files_and_duplicate_fields():
    response = client.post('/api/learn', data={'question':'미분','format':'html'}, files=[('file',('a.png',PNG,'image/png')),('file',('b.png',PNG,'image/png'))])
    assert response.status_code == 400
    response = client.post('/api/learn',files=[('question',(None,'미분')),('format',(None,'html')),('format',(None,'shorts'))])
    assert response.status_code == 422
    assert client.post('/api/learn',json={'question':'미분'}).status_code == 415


def test_upload_filename_is_only_a_name():
    response=client.post('/api/learn',data={'question':'미분','format':'html'},files={'file':('../../secret.pdf',pdf_bytes(),'application/pdf')})
    assert response.json()['material']['filename'] == 'secret.pdf'
