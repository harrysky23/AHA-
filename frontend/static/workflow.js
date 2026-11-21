(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const form = $('learn-form');
  const fileInput = $('material');
  const submit = $('generate');
  let busy = false;
  let fileError = '';
  let lastResult = null;
  const scrollBehavior = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
  const formats = new Map([['pdf', 'application/pdf'], ['png', 'image/png'], ['jpg', 'image/jpeg'], ['jpeg', 'image/jpeg'], ['webp', 'image/webp']]);
  window.addEventListener('message', (event) => {
    const iframe = $('lesson-view').querySelector('iframe');
    // Sandboxed documents have an opaque origin. Check the exact sending window
    // and bound the only permitted message, rather than granting same-origin.
    if (!iframe || event.source !== iframe.contentWindow || event.origin !== 'null') return;
    if (event.data?.type !== 'aha:lesson-size' || !Number.isFinite(event.data.height)) return;
    if (event.data.height < 300 || event.data.height > 2200) return;
    iframe.style.height = `${Math.ceil(event.data.height) + 4}px`;
  });
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
    if (data.mode !== 'local_demo' || !['html', 'shorts'].includes(data.format)) throw new Error('지원하지 않는 학습 응답이에요.');
    if (data.format === 'html' && data.lesson?.viewer_url !== '/lessons/secant-tangent') throw new Error('학습 예제 주소를 확인할 수 없어요.');
    if (data.format === 'shorts' && data.video?.url !== '/static/media/derivative-explainer.mp4') throw new Error('영상 예제 주소를 확인할 수 없어요.');
    $('result-video').pause();
    $('result-video').removeAttribute('src'); $('result-video').load();
    $('lesson-view').replaceChildren();
    $('request-summary').replaceChildren();
    $('result-title').textContent = data.title;
    $('result-mode').textContent = data.fallback ? '기본 예제 · API 연결 없이 열기' : '로컬 예제 · AI 생성 아님';
    $('result-notice').textContent = data.notice;
    appendSummary('개념', data.request.concept || '입력하지 않음');
    appendSummary('질문', data.request.question || '입력하지 않음');
    appendSummary('학습 자료', data.material ? `${data.material.filename} · ${data.material.size_bytes.toLocaleString()} bytes · 내용 분석 안 됨` : '없음');
    $('grounding-note').textContent = data.grounding.message;
    $('video-view').hidden = data.format !== 'shorts';
    if (data.format === 'html') {
      const iframe = document.createElement('iframe');
      iframe.title = '수학 II 할선에서 접선으로 인터랙티브 학습';
      iframe.setAttribute('sandbox', 'allow-scripts');
      iframe.setAttribute('allow', "camera 'none'; microphone 'none'; geolocation 'none'");
      iframe.referrerPolicy = 'no-referrer';
      iframe.src = data.lesson.viewer_url;
      $('lesson-view').append(iframe);
    } else {
      $('video-note').textContent = data.video.notice;
      $('result-video').src = data.video.url;
    }
    lastResult = data;
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
    render({...lastResult, format:'html', video:null, lesson:{viewer_url:'/lessons/secant-tangent'}});
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
    const body = new FormData();
    body.set('concept', concept); body.set('question', question); body.set('format', form.elements.format.value);
    if (fileInput.files[0]) body.set('file', fileInput.files[0]);
    busy = true; submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    const controls = [...form.querySelectorAll('input,textarea,button')].filter(el => el !== submit);
    controls.forEach(el => { el.disabled = true; });
    $('learning-result').hidden = true; $('result-video').pause(); $('lesson-view').replaceChildren();
    submit.textContent = '학습 결과 불러오는 중…'; $('request-status').textContent = '로컬 서버에서 입력을 확인하고 있어요.';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch('/api/learn', {method:'POST', body, signal:controller.signal});
      const data = await response.json();
      if (!response.ok) {
        showError(typeof data.detail === 'string' ? data.detail : '입력 내용을 확인해 주세요.', response.status >= 500);
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
