(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const form = $('learn-form');
  const fileInput = $('material');
  const submit = $('generate');
  let busy = false;
  let fileError = '';
  let serverMode = 'mock';
  let videoRenderer = 'svg';
  let consentProvider = '';
  const isClaudeVideo = () => videoRenderer === 'claude' && form.elements.format.value === 'shorts';
  let timeoutMilliseconds = 105000;
  const scrollBehavior = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
  const formats = new Map([['pdf', 'application/pdf'], ['png', 'image/png'], ['jpg', 'image/jpeg'], ['jpeg', 'image/jpeg'], ['webp', 'image/webp'], ['txt', 'text/plain']]);
  const fileMime = (file) => formats.get(file?.name.split('.').pop().toLowerCase());
  const usesGeminiImage = () => serverMode === 'gemini' && form.elements.format.value === 'html'
    && fileMime(fileInput.files[0])?.startsWith('image/');
  const originalAccept = fileInput.accept;
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
    $('generation-mode').textContent = isGemini ? 'Gemini AI · 질문에 맞춘 실습' : mode === 'elice' ? 'Elice · 향후 연결 예정' : 'mock · 고정 수학 예제, AI 아님';
    $('mode-note').textContent = isGemini ? '성인 개발·평가용 Gemini 모드예요. 질문과 PDF 추출 텍스트로 설명을 구성하며 같은 입력은 캐시를 재사용해요.' : mode === 'elice' ? 'Elice는 실제 API 사양 확정 후 연결할 예정이에요. 현재 네트워크 호출은 하지 않아요.' : 'mock 모드는 질문과 관계없이 고정 수학 II 예제를 사용해요. 실제 AI 분석이나 학습 수준 진단은 아니에요.';
    $('request-status').textContent = mode === 'elice' ? 'Elice는 아직 연결되지 않았어요. mock 또는 gemini로 설정해 주세요.' : !configured ? 'Gemini 인증 설정이 준비되지 않았어요. 서버 .env의 API 키를 확인해 주세요.' : isGemini ? 'Gemini 전송 안내를 확인한 뒤 학습 결과를 열어 주세요.' : 'mock 모드에서는 API 키 없이 체험할 수 있어요.';
    $('consent-option').hidden = !isGemini;
    const banner = document.querySelector('.phase-banner');
    if (banner) banner.textContent = isGemini ? '성인 개발·평가용 Gemini AI · 인터랙티브 학습과 새 숏츠 생성' : mode === 'elice' ? 'Elice 연결은 준비 중입니다. 기존 데모와 예시 영상을 이용할 수 있어요.' : 'mock 스토리보드 + 실제 로컬 영상 렌더링 · 외부 AI 호출 없음';
    updateFormat();
  }
  function updateFormat() {
    const shorts=form.elements.format.value==='shorts';
    const claude = isClaudeVideo();
    const provider = claude ? 'chatkhu' : serverMode === 'gemini' ? 'gemini' : '';
    if (provider !== consentProvider) $('external-consent').checked = false;
    consentProvider = provider;
    $('consent-option').hidden = !provider;
    $('gemini-consent-copy').hidden = provider !== 'gemini';
    $('chatkhu-consent-copy').hidden = provider !== 'chatkhu';
    const image = usesGeminiImage() && !fileError;
    $('image-consent-option').hidden = !image;
    if (!image) $('image-consent').checked = false;
    fileInput.accept = originalAccept + (claude ? ',.txt,text/plain' : '');
    $('video-renderer-note').hidden = claude;
    $('video-duration').disabled = claude;
    $('shorts-options').hidden=!shorts;
    $('scope-title').textContent=shorts?'핵심 개념을 장면으로 연결해요':serverMode==='gemini'?'입력한 개념을 직접 탐색해요':'이번에는 이 개념을 배워요';
    $('scope-description').textContent=shorts?'수학·과학·사회·정보 개념을 30–60초의 세로형 영상으로 구성해요. 어려운 표현은 텍스트 설명으로 바꿀 수 있어요.':serverMode==='gemini'?'질문에 어울리는 그래프, 과정, 비교 등으로 직접 탐색하고 확인 문제를 풀 수 있어요.':'수학 II · f(x)=x², 점 P(1,1)에서 할선의 기울기 2+h → 접선의 기울기 2';
    $('mode-note').textContent=serverMode==='gemini'?'질문과 PDF 추출 텍스트로 설명을 구성하며 같은 입력의 생성 명세는 캐시를 재사용해요.':serverMode==='elice'?'Elice는 실제 API 사양 확정 후 연결할 예정이에요.':shorts?'mock은 네 가지 개념의 스토리보드 예제를 실제 영상으로 만들어요. AI 분석 결과가 아니에요.':'mock은 질문과 관계없이 고정 수학 II 예제를 사용해요. AI 분석 결과가 아니에요.';
    $('question-note').textContent=shorts?'개념이나 질문 중 하나를 입력해 주세요. mock 예제: 미분계수, 물의 순환, 수요와 공급, 이진 탐색.':'개념이나 질문 중 하나를 입력해 주세요. 특히 헷갈리는 부분을 적으면 실습에 반영할 수 있어요.';
    if (image) {
      $('mode-note').textContent = '질문과 첨부 이미지의 내용을 바탕으로 실습을 구성해요.';
      $('question-note').textContent = '사진만으로도 실습을 만들 수 있어요. 특정 부분이 헷갈리면 질문을 함께 적어 주세요.';
    }
    if (claude) {
      $('scope-description').textContent = 'Claude가 질문에 맞춰 약 30초 분량의 대본과 모션그래픽을 만들어요.';
      $('mode-note').textContent = 'PDF, 이미지 또는 UTF-8 텍스트 파일을 참고 자료로 올릴 수 있어요.';
      $('question-note').textContent = '개념이나 질문 중 하나를 입력해 주세요.';
      $('video-duration').value = '30';
    }
    submit.disabled=busy || (shorts && window.AHAVideo?.active===true);
    submit.textContent=shorts?'나만의 숏츠 만들기 →':'학습 결과 열기 →';
  }
  form.querySelectorAll('[name=format]').forEach(input => input.addEventListener('change', () => {
    clearError();
    updateFormat();
  }));
  window.addEventListener('aha:video-active',updateFormat);
  fetch('/api/health').then(response => {
    if (!response.ok) throw new Error('health');
    return response.json();
  }).then(data => {
    if (!['mock','gemini','elice'].includes(data.mode)) throw new Error('mode');
    if (Number.isFinite(data.request_timeout_seconds)) timeoutMilliseconds = Math.min(110000, Math.max(15000, data.request_timeout_seconds * 1000));
    videoRenderer = data.video_renderer;
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
    $('use-shorts').hidden = true;
  }
  function checkFile() {
    const file = fileInput.files[0];
    fileError = '';
    $('remove-file').hidden = !file;
    if (!file) {
      $('file-status').textContent = '자료 없이 질문만 입력해도 괜찮아요.';
      return;
    }
    const expected = fileMime(file);
    if (!expected || (expected === 'text/plain' && !isClaudeVideo()) || (file.type && expected !== file.type)) fileError = isClaudeVideo() ? 'PDF, PNG, JPEG, WebP, TXT 파일을 선택해 주세요.' : 'PDF, PNG, JPEG, WebP 파일을 선택해 주세요.';
    else if (!file.size) fileError = '빈 파일은 올릴 수 없어요.';
    else if (file.size > 5 * 1024 * 1024) fileError = '파일은 5MB 이하로 올려 주세요.';
    $('file-status').textContent = fileError || `${file.name} · ${(file.size / 1024).toFixed(1)}KB · 선택 완료`;
  }
  function updateFile() {
    $('image-consent').checked = false;
    clearError();
    checkFile();
    updateFormat();
  }
  fileInput.addEventListener('change', updateFile);
  $('remove-file').addEventListener('click', () => { fileInput.value = ''; updateFile(); });
  $('sample-input').addEventListener('click', () => {
    $('concept').value = '미분계수의 기하학적 의미';
    $('question').value = 'f(x)=x²의 점 P(1,1)에서 할선의 기울기는 왜 접선의 기울기 2에 가까워지나요?';
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
    if (data.format === 'html' && !['/lessons/secant-tangent', '/lessons/interactive'].includes(data.lesson?.viewer_url)) throw new Error('학습 예제 주소를 확인할 수 없어요.');
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
    const material = data.material;
    const materialStatus = material?.sent_to_provider
      ? (material.content_type.startsWith('image/') ? 'Gemini에 이미지 전달' : 'Gemini에 추출 텍스트 전달')
      : material?.analyzed && data.generation?.cached ? '같은 자료의 캐시 재사용'
      : material?.text_extracted ? '텍스트 추출 완료' : '내용 분석 안 됨';
    appendSummary('학습 자료', material ? `${material.filename} · ${material.size_bytes.toLocaleString()} bytes · ${materialStatus}` : '없음');
    $('grounding-note').textContent = data.grounding.message;
    $('verification-note').hidden = !data.verification;
    $('verification-note').textContent = data.verification?.notice || '';
    if (data.generation?.request_id) appendSummary('요청 ID', data.generation.request_id);
    $('video-view').hidden = data.format !== 'shorts';
    if (data.format === 'html') {
      const iframe = document.createElement('iframe');
      iframe.title = data.lesson.viewer_url === '/lessons/interactive' ? `${data.title} 인터랙티브 학습` : '수학 II 할선에서 접선으로 인터랙티브 학습';
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
  $('use-shorts').addEventListener('click', () => {
    form.elements.format.value = 'shorts';
    clearError();
    updateFormat();
    $('request-status').textContent = '질문과 자료를 유지했어요. 전송 안내를 확인한 뒤 숏츠를 생성할 수 있어요.';
    if (consentProvider) $('external-consent').focus();
    else submit.focus();
  });
  window.addEventListener('aha:sample-video',()=>render({mode:'local_demo',format:'shorts',title:'미분계수 · 기존 예시 영상',
    request:{concept:$('concept').value.trim(),question:$('question').value.trim()},material:null,
    notice:'기존 시안에 포함된 예시 영상이에요. 새로 생성한 결과가 아니에요.',grounding:{message:'입력한 질문과 자료는 이 예시 영상에 사용하지 않아요.'},
    video:{url:'/static/media/derivative-explainer.mp4',notice:'기존 예시 영상 · 새 생성 아님'}}));
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
    const image = usesGeminiImage();
    if (!concept && !question && !image) { showError('어려운 개념 또는 질문을 입력해 주세요. 예시 질문도 사용할 수 있어요.'); $('concept').focus(); return; }
    if (consentProvider && !$('external-consent').checked) {
      showError(consentProvider === 'chatkhu' ? 'ChatKHU 전송 및 크레딧 안내를 확인하고 체크해 주세요.' : 'Gemini 전송 안내를 확인하고 체크해 주세요.');
      $('external-consent').focus(); return;
    }
    if (image && !$('image-consent').checked) {
      showError('첨부 이미지 원본의 Gemini 전송에 동의해 주세요.');
      $('image-consent').focus(); return;
    }
    const body = new FormData();
    const isShorts = form.elements.format.value === 'shorts';
    body.set('concept', concept); body.set('question', question);
    body.set('format', isShorts ? 'shorts' : serverMode === 'gemini' ? 'interactive' : 'html');
    if ($('external-consent').checked) body.set('consent', 'true');
    if (image) body.set('image_consent', 'true');
    if (fileInput.files[0]) body.set('file', fileInput.files[0]);
    if (isShorts) { body.set('student_level',$('video-level').value); body.set('target_duration_seconds',$('video-duration').value); }
    busy = true; submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    const controls = [...form.querySelectorAll('input,textarea,button,select')].filter(el => el !== submit);
    controls.forEach(el => { el.disabled = true; });
    $('learning-result').hidden = true; $('result-video').pause(); $('lesson-view').replaceChildren();
    submit.textContent = '학습 결과 불러오는 중…'; $('request-status').textContent = '로컬 서버에서 입력을 확인하고 있어요.';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMilliseconds);
    try {
      if (isShorts) {
        await window.AHAVideo.start(body);
        $('request-status').textContent='영상 생성 요청을 접수했어요. 아래 카드에서 진행 상태를 확인해 주세요.';
        return;
      }
      const response = await fetch('/api/learn', {method:'POST', body, signal:controller.signal});
      const data = await response.json();
      if (!response.ok) {
        if (data.code === 'consent_required') updateMode('gemini');
        if (data.code === 'unsupported_scope') {
          showError('인터랙티브 학습은 f(x)=x²의 점 P(1,1)에서 할선과 접선을 다뤄요. 같은 질문을 숏츠로 옮기거나 기본 수학 예제를 열 수 있어요.', true);
          $('use-shorts').hidden = false;
          $('request-status').textContent = '이 질문에는 숏츠 학습을 선택할 수 있어요.';
          return;
        }
        showError(typeof data.detail === 'string' ? data.detail : '입력 내용을 확인해 주세요.', data.fallback_available === true || response.status >= 500);
        $('request-status').textContent = '결과를 열지 못했어요. 입력 확인 후 다시 시도해 주세요.';
        return;
      }
      render(data);
      $('request-status').textContent = '학습 결과를 열었어요. 아래에서 학습을 시작해 보세요.';
    } catch (error) {
      if (error.code==='consent_required') updateMode('gemini');
      showError(error.code ? error.message : error.name === 'AbortError' ? '응답 시간이 초과됐어요. 다시 시도하거나 기본 예제를 열어 주세요.' : '로컬 서버에 연결하지 못했거나 응답을 읽을 수 없어요. 서버 실행 상태를 확인해 주세요.', true);
      $('request-status').textContent = '연결 후 다시 시도할 수 있어요.';
    } finally {
      clearTimeout(timeout); busy = false; submit.disabled = false;
      controls.forEach(el => { el.disabled = false; });
      form.removeAttribute('aria-busy'); updateFormat();
    }
  });
})();
