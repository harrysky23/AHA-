(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const form = $('learn-form');
  const fileInput = $('material');
  const submit = $('generate');
  let busy = false;
  let fileError = '';
  let serverMode = 'mock';
  let timeoutMilliseconds = 105000;
  const scrollBehavior = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
  const formats = new Map([['pdf', 'application/pdf'], ['png', 'image/png'], ['jpg', 'image/jpeg'], ['jpeg', 'image/jpeg'], ['webp', 'image/webp']]);
  window.addEventListener('message', (event) => {
    const iframe = $('lesson-view').querySelector('iframe');
    // Sandboxed documents have an opaque origin. Check the exact sending window
    // and bound the only permitted message, rather than granting same-origin.
    if (!iframe || event.source !== iframe.contentWindow || event.origin !== 'null') return;
    if (event.data?.type !== 'aha:lesson-size' || !Number.isFinite(event.data.height)) return;
    if (event.data.height < 300 || event.data.height > 12000) return;
    iframe.style.height = `${Math.ceil(event.data.height) + 4}px`;
  });
  function updateMode(mode, configured = true) {
    serverMode = mode;
    const isGemini = mode === 'gemini';
    $('generation-mode').textContent = isGemini ? 'Gemini AI · 검증된 그래프 컴포넌트' : mode === 'elice' ? 'Elice · 향후 연결 예정' : 'mock · 고정 수학 예제, AI 아님';
    $('mode-note').textContent = isGemini ? '성인 개발·평가용 Gemini 모드예요. 질문과 PDF 추출 텍스트로 설명을 구성하며 같은 입력은 캐시를 재사용해요.' : mode === 'elice' ? 'Elice는 실제 API 사양 확정 후 연결할 예정이에요. 현재 네트워크 호출은 하지 않아요.' : 'mock 모드는 질문과 관계없이 고정 수학 II 예제를 사용해요. 실제 AI 분석이나 학습 수준 진단은 아니에요.';
    $('request-status').textContent = mode === 'elice' ? 'Elice는 아직 연결되지 않았어요. mock 또는 gemini로 설정해 주세요.' : !configured ? 'Gemini 인증 설정이 준비되지 않았어요. 서버 .env의 API 키를 확인해 주세요.' : isGemini ? 'Gemini 전송 안내를 확인한 뒤 학습 결과를 열어 주세요.' : 'mock 모드에서는 API 키 없이 체험할 수 있어요.';
    $('consent-option').hidden = !isGemini || form.elements.format.value !== 'html';
    const banner = document.querySelector('.phase-banner');
    if (banner) banner.textContent = isGemini ? 'Phase 2 · 성인 개발·평가용 Gemini AI + 수학 II 학습. 새 숏츠 생성은 준비 중입니다.' : mode === 'elice' ? 'Elice 연결은 준비 중입니다. 기존 수학 데모와 예시 영상은 계속 이용할 수 있어요.' : 'Phase 2 · mock 고정 예제 모드입니다. 실제 AI 호출은 하지 않습니다.';
  }
  form.querySelectorAll('[name=format]').forEach(input => input.addEventListener('change', () => {
    $('consent-option').hidden = serverMode !== 'gemini' || form.elements.format.value !== 'html';
  }));
  fetch('/api/health').then(response => {
    if (!response.ok) throw new Error('health');
    return response.json();
  }).then(data => {
    if (!['mock','gemini','elice'].includes(data.mode)) throw new Error('mode');
    if (Number.isFinite(data.request_timeout_seconds)) timeoutMilliseconds = Math.min(110000, Math.max(15000, data.request_timeout_seconds * 1000));
    updateMode(data.mode, data.ai_configured);
  }).catch(() => { $('request-status').textContent = '서버 모드를 확인하지 못했어요. 제출 후 오류가 발생하면 기본 예제를 열 수 있어요.'; });
  function showError(message, fallback = false) {
    $('request-error').textContent = message;
    $('request-error').hidden = false;
    $('fallback').hidden = !fallback;
  }
  function clearError() {
    $('request-error').hidden = true;
    $('fallback').hidden = true;
  }
  function checkFile() {
    const file = fileInput.files[0];
    fileError = '';
    $('remove-file').hidden = !file;
    if (!file) {
      $('file-status').textContent = '자료 없이 질문만 입력해도 괜찮아요.';
      return;
    }
    const expected = formats.get(file.name.split('.').pop().toLowerCase());
    if (!expected || (file.type && expected !== file.type)) fileError = 'PDF, PNG, JPEG, WebP 파일을 선택해 주세요.';
    else if (!file.size) fileError = '빈 파일은 올릴 수 없어요.';
    else if (file.size > 5 * 1024 * 1024) fileError = '파일은 5MB 이하로 올려 주세요.';
    $('file-status').textContent = fileError || `${file.name} · ${(file.size / 1024).toFixed(1)}KB · 선택 완료`;
  }
  fileInput.addEventListener('change', () => { clearError(); checkFile(); });
  $('remove-file').addEventListener('click', () => { fileInput.value = ''; checkFile(); clearError(); });
  $('sample-input').addEventListener('click', () => {
    $('concept').value = '미분계수의 기하학적 의미';
    $('question').value = 'f(x)=x²에서 두 점을 잇는 할선의 기울기가 왜 접선의 기울기 2에 가까워지나요?';
    $('concept').focus(); clearError();
  });
  function appendSummary(label, value) {
    const term = document.createElement('dt'); term.textContent = label;
    const detail = document.createElement('dd'); detail.textContent = value;
    $('request-summary').append(term, detail);
  }
  function render(data) {
    // Only locally owned, allowlisted viewers are accepted. Never inject response HTML.
    if (!['local_demo','mock','gemini'].includes(data.mode) || !['html', 'shorts'].includes(data.format)) throw new Error('지원하지 않는 학습 응답이에요.');
    if (data.format === 'html' && data.lesson?.viewer_url !== '/lessons/secant-tangent') throw new Error('학습 예제 주소를 확인할 수 없어요.');
    if (data.format === 'shorts' && data.video?.url !== '/static/media/derivative-explainer.mp4') throw new Error('영상 예제 주소를 확인할 수 없어요.');
    $('result-video').pause();
    $('result-video').removeAttribute('src'); $('result-video').load();
    $('lesson-view').replaceChildren();
    $('request-summary').replaceChildren();
    $('result-title').textContent = data.title;
    $('result-mode').textContent = data.fallback ? '기본 예제 · API 연결 없이 열기' : data.mode === 'gemini' ? (data.generation?.cached ? 'Gemini AI · 캐시 재사용' : 'Gemini AI · 구조화 명세 검증 통과') : data.mode === 'mock' ? 'mock · 고정 예제, AI 아님' : '기존 예시 영상 · 새 생성 아님';
    $('result-notice').textContent = data.notice;
    appendSummary('개념', data.request.concept || '입력하지 않음');
    appendSummary('질문', data.request.question || '입력하지 않음');
    appendSummary('학습 자료', data.material ? `${data.material.filename} · ${data.material.size_bytes.toLocaleString()} bytes · ${data.material.sent_to_provider ? 'Gemini에 추출 텍스트 전달' : data.material.analyzed && data.generation?.cached ? '같은 자료의 캐시 재사용, 이번에는 전송 안 함' : data.material.text_extracted ? '텍스트 추출 완료' : '내용 분석 안 됨'}` : '없음');
    $('grounding-note').textContent = data.grounding.message;
    $('verification-note').hidden = !data.verification;
    $('verification-note').textContent = data.verification?.notice || '';
    if (data.generation?.request_id) appendSummary('요청 ID', data.generation.request_id);
    $('video-view').hidden = data.format !== 'shorts';
    if (data.format === 'html') {
      const iframe = document.createElement('iframe');
      iframe.title = '수학 II 할선에서 접선으로 인터랙티브 학습';
      iframe.setAttribute('sandbox', 'allow-scripts');
      iframe.setAttribute('allow', "camera 'none'; microphone 'none'; geolocation 'none'");
      iframe.referrerPolicy = 'no-referrer';
      if (data.lesson.spec) {
        iframe.addEventListener('load', () => {
          iframe.contentWindow.postMessage({type:'aha:lesson-spec', spec:data.lesson.spec}, '*');
        }, {once:true});
      }
      iframe.src = data.lesson.viewer_url;
      $('lesson-view').append(iframe);
    } else {
      $('video-note').textContent = data.video.notice;
      $('result-video').src = data.video.url;
    }
    $('learning-result').hidden = false;
    $('learning-result').focus({preventScroll:true});
    $('learning-result').scrollIntoView({behavior:scrollBehavior(), block:'start'});
  }
  function fallback() {
    render({
      mode: 'local_demo', format: 'html', fallback: true,
      title: '수학 II · 할선에서 접선으로',
      request: {concept: $('concept').value.trim(), question: $('question').value.trim()},
      material: null,
      notice: '기본 수학 예제입니다. API 요청 성공이나 자료 분석을 의미하지 않아요. f(x)=x², a=1인 고정 예제를 사용해요.',
      grounding: {message: '선택한 파일은 이 기본 예제에 사용하지 않아요. 로컬 서버가 실행 중이어야 예제를 열 수 있어요.'},
      lesson: {viewer_url:'/lessons/secant-tangent'},
    });
  }
  $('fallback').addEventListener('click', fallback);
  $('switch-html').addEventListener('click', () => {
    form.elements.format.value = 'html';
    $('consent-option').hidden = serverMode !== 'gemini';
    fallback();
  });
  $('edit-input').addEventListener('click', () => {
    $('result-video').pause();
    $('concept').focus({preventScroll:true});
    $('learn-form').scrollIntoView({behavior:scrollBehavior(), block:'start'});
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    clearError(); checkFile();
    if (fileError) { showError(fileError); fileInput.focus(); return; }
    const concept = $('concept').value.trim();
    const question = $('question').value.trim();
    if (!concept && !question) { showError('어려운 개념 또는 질문을 입력해 주세요. 예시 질문도 사용할 수 있어요.'); $('concept').focus(); return; }
    if (serverMode === 'gemini' && form.elements.format.value === 'html' && !$('external-consent').checked) {
      showError('Gemini 전송 안내를 확인하고 체크해 주세요.');
      $('external-consent').focus(); return;
    }
    const body = new FormData();
    body.set('concept', concept); body.set('question', question); body.set('format', form.elements.format.value);
    if ($('external-consent').checked) body.set('consent', 'true');
    if (fileInput.files[0]) body.set('file', fileInput.files[0]);
    busy = true; submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    const controls = [...form.querySelectorAll('input,textarea,button')].filter(el => el !== submit);
    controls.forEach(el => { el.disabled = true; });
    $('learning-result').hidden = true; $('result-video').pause(); $('lesson-view').replaceChildren();
    submit.textContent = '학습 결과 불러오는 중…'; $('request-status').textContent = '로컬 서버에서 입력을 확인하고 있어요.';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMilliseconds);
    try {
      const response = await fetch('/api/learn', {method:'POST', body, signal:controller.signal});
      const data = await response.json();
      if (!response.ok) {
        if (data.code === 'consent_required') updateMode('gemini');
        showError(typeof data.detail === 'string' ? data.detail : '입력 내용을 확인해 주세요.', data.fallback_available === true || response.status >= 500);
        $('request-status').textContent = '결과를 열지 못했어요. 입력 확인 후 다시 시도해 주세요.';
        return;
      }
      render(data);
      $('request-status').textContent = '학습 결과를 열었어요. 아래에서 학습을 시작해 보세요.';
    } catch (error) {
      showError(error.name === 'AbortError' ? '응답 시간이 초과됐어요. 다시 시도하거나 기본 예제를 열어 주세요.' : '로컬 서버에 연결하지 못했거나 응답을 읽을 수 없어요. 서버 실행 상태를 확인해 주세요.', true);
      $('request-status').textContent = '연결 후 다시 시도할 수 있어요.';
    } finally {
      clearTimeout(timeout); busy = false; submit.disabled = false;
      controls.forEach(el => { el.disabled = false; });
      form.removeAttribute('aria-busy'); submit.textContent = '학습 결과 열기 →';
    }
  });
})();
