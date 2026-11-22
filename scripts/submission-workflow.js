/* Local-only controller for the exported submission; no API requests. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const form = $('learn-form');
  const material = $('material');
  const assets = window.AHASubmission;
  const decode = value => new TextDecoder().decode(Uint8Array.from(atob(value), c => c.charCodeAt(0)));
  const scrollTo = node => node.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start'});
  let fileError = '';

  function clearError() {
    $('request-error').hidden = true;
  }
  function updateFile() {
    clearError();
    const file = material.files[0];
    fileError = '';
    $('remove-file').hidden = !file;
    if (!file) {
      $('file-status').textContent = '자료 없이 질문만 입력해도 괜찮아요.';
      return;
    }
    const types = {pdf:'application/pdf', png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg', webp:'image/webp'};
    const mime = types[file.name.split('.').pop().toLowerCase()];
    if (!mime || (file.type && file.type !== mime)) fileError = 'PDF, PNG, JPEG, WebP 파일을 선택해 주세요.';
    else if (!file.size) fileError = '빈 파일은 선택할 수 없어요.';
    else if (file.size > 5 * 1024 * 1024) fileError = '파일은 5MB 이하로 선택해 주세요.';
    $('file-status').textContent = fileError || `${file.name} · ${(file.size / 1024).toFixed(1)}KB · 선택 완료 (내용 분석 안 됨)`;
  }
  function updateFormat() {
    const shorts = form.elements.format.value === 'shorts';
    $('shorts-options').hidden = !shorts;
    $('generate').textContent = shorts ? '기존 예시 영상 열기 →' : '인터랙티브 예제 열기 →';
    $('scope-title').textContent = shorts ? '기존 예시 영상으로 학습해요' : '이번에는 이 개념을 배워요';
    $('scope-description').textContent = shorts ? '시안에 포함된 미분계수 설명 영상을 재생해요. 질문이나 자료로 새 영상을 생성하지 않아요.' : '수학 II · f(x)=x², 점 P(1,1)에서 할선의 기울기 2+h → 접선의 기울기 2';
    clearError();
  }
  function appendSummary(label, value) {
    const dt = document.createElement('dt'); dt.textContent = label;
    const dd = document.createElement('dd'); dd.textContent = value;
    $('request-summary').append(dt, dd);
  }
  function showResult(shorts) {
    $('result-video').pause();
    $('result-video').removeAttribute('src');
    $('result-video').load();
    $('lesson-view').replaceChildren();
    $('request-summary').replaceChildren();
    $('result-title').textContent = shorts ? '미분계수 · 기존 예시 영상' : '수학 II · 할선에서 접선으로';
    $('result-mode').textContent = shorts ? '기존 예시 영상 · 새 생성 아님' : '제출용 로컬 예제 · API 연결 없음';
    $('result-notice').textContent = '프론트 체험용 제출본입니다. 입력한 질문과 파일로 AI 분석이나 콘텐츠 생성을 수행하지 않으며, 미리 준비된 예제를 보여 줍니다.';
    appendSummary('개념', $('concept').value.trim() || '입력하지 않음');
    appendSummary('질문', $('question').value.trim() || '입력하지 않음');
    const file = material.files[0];
    appendSummary('학습 자료', file ? `${file.name} · ${file.size.toLocaleString()} bytes · 선택만 완료, 내용 분석 안 됨` : '없음');
    $('grounding-note').textContent = '질문과 파일 정보는 화면에만 표시돼요. 파일 내용을 읽거나 서버·외부 API로 전송하지 않아요. 예제는 f(x)=x², a=1인 고정 시나리오예요.';
    $('verification-note').hidden = true;
    $('video-view').hidden = !shorts;
    if (shorts) {
      $('video-note').textContent = '원본 시안의 기존 가로형 예시 영상이에요. 새로 생성한 9:16 숏츠가 아니에요.';
      $('result-video').src = assets.derivativeVideo;
    } else {
      const iframe = document.createElement('iframe');
      iframe.title = '수학 II 할선에서 접선으로 인터랙티브 학습';
      iframe.setAttribute('sandbox', 'allow-scripts');
      iframe.setAttribute('allow', "camera 'none'; microphone 'none'; geolocation 'none'");
      iframe.referrerPolicy = 'no-referrer';
      iframe.srcdoc = decode(assets.lesson);
      $('lesson-view').append(iframe);
    }
    $('learning-result').hidden = false;
    $('learning-result').focus({preventScroll:true});
    scrollTo($('learning-result'));
    $('request-status').textContent = '기존 예제를 열었어요. 아래에서 학습을 시작해 보세요.';
  }
  window.addEventListener('message', event => {
    const iframe = $('lesson-view').querySelector('iframe');
    if (!iframe || event.source !== iframe.contentWindow || event.origin !== 'null') return;
    if (event.data?.type !== 'aha:lesson-size' || !Number.isFinite(event.data.height)) return;
    if (event.data.height < 300 || event.data.height > 12000) return;
    iframe.style.height = `${Math.ceil(event.data.height) + 4}px`;
  });
  material.addEventListener('change', updateFile);
  $('remove-file').addEventListener('click', () => { material.value = ''; updateFile(); });
  $('sample-input').addEventListener('click', () => {
    $('concept').value = '미분계수의 기하학적 의미';
    $('question').value = 'f(x)=x²의 점 P(1,1)에서 할선의 기울기는 왜 접선의 기울기 2에 가까워지나요?';
    $('concept').focus(); clearError();
  });
  form.querySelectorAll('[name=format]').forEach(input => input.addEventListener('change', updateFormat));
  $('shorts-sample').addEventListener('click', () => showResult(true));
  $('switch-html').addEventListener('click', () => {
    form.elements.format.value = 'html'; updateFormat(); showResult(false);
  });
  $('edit-input').addEventListener('click', () => {
    $('result-video').pause();
    $('concept').focus({preventScroll:true}); scrollTo(form);
  });
  form.addEventListener('submit', event => {
    event.preventDefault(); updateFile();
    const missingQuestion = !$('concept').value.trim() && !$('question').value.trim();
    if (fileError || missingQuestion) {
      $('request-error').textContent = fileError || '어려운 개념 또는 질문을 입력해 주세요. 예시 질문도 사용할 수 있어요.';
      $('request-error').hidden = false;
      (fileError ? material : $('concept')).focus();
      return;
    }
    showResult(form.elements.format.value === 'shorts');
  });
  updateFormat();
})();
