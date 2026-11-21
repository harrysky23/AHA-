/* Session-owned local jobs. Only the job ID is persisted; never questions/files. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), storageKey = 'aha:video-job';
  const terminal = new Set(['completed', 'failed', 'cancelled']);
  const labels = {queued:'생성 순서를 기다리고 있어요', analyzing:'학습 자료 분석 중', storyboard:'영상 구성 중',
    code:'Claude가 대본과 애니메이션을 작성 중', code_repair:'Claude가 애니메이션 오류를 수정 중',
    waiting_renderer:'영상 생성기를 기다리고 있어요', tts:'음성 및 애니메이션 생성 중', browser:'음성 및 애니메이션 생성 중',
    frames:'음성 및 애니메이션 생성 중', encode:'영상 인코딩 중', verify:'영상 파일 검사 중', ready:'영상 준비 완료',
    failed:'영상 생성에 실패했어요', cancelled:'영상 생성을 취소했어요'};
  let current = null, active = false, timer, sequence = 0, applied = 0, displayedURL = null;
  function remember(id) { try { id ? localStorage.setItem(storageKey,id) : localStorage.removeItem(storageKey); } catch {} }
  function setActive(value) { active = value; window.dispatchEvent(new CustomEvent('aha:video-active')); }
  function clearPlayer() { $('generated-video').pause(); $('generated-video').removeAttribute('src'); $('generated-video').load(); displayedURL=null; $('generated-video-view').hidden=true; $('video-download').removeAttribute('href'); }
  function error(message) { $('video-job-error').textContent=message; $('video-job-error').hidden=false; }
  function accept(data, seq) {
    if (data.job_id!==current || seq<applied) return;
    applied=seq;
    if (!['queued','generating','rendering','completed','failed','cancelled'].includes(data.status)) throw Error('invalid status');
    $('video-job').hidden=false; $('video-job-error').hidden=true; $('video-resume').hidden=true;
    setActive(!terminal.has(data.status));
    $('video-job-stage').textContent=data.cancel_requested && active ? '프로세스 종료와 파일 정리를 확인 중이에요' : labels[data.stage] || '영상 작업 상태를 확인하고 있어요';
    const p=data.progress || {};
    $('video-job-detail').textContent=Number.isInteger(p.frames_done)&&Number.isInteger(p.frames_total) ? `캡처한 프레임 ${p.frames_done} / ${p.frames_total} · 전체 작업의 진행률은 아니에요.` : active ? '실제 처리 단계를 표시합니다. 창을 닫거나 새로고침해도 작업은 계속돼요.' : '';
    $('video-cancel').hidden=!active; $('video-cancel').disabled=data.cancel_requested;
    $('video-retry').hidden=active || data.status==='completed';
    $('video-delete').disabled=false;
    if (data.error) error(`${data.error.phase==='generation'?'영상 구성':'영상 렌더링'} 단계: ${data.error.message} (${data.error.code})`);
    if (data.status==='completed') {
      const url=`/api/videos/${current}/file`;
      if (data.video_url!==url) throw Error('invalid video URL');
      if (displayedURL!==url) { $('generated-video').src=url; displayedURL=url; }
      $('generated-video-view').hidden=false;
      $('video-download').href=url+'?download=1';
      const note = data.result?.mode === 'claude_code' ? 'Claude가 작성한 애니메이션을 렌더링했어요. 설명의 정확성을 검토해 주세요.' : data.result?.mode === 'mock' ? 'mock 스토리보드 예제를 실제로 렌더링한 영상이에요. AI 분석 결과는 아니에요.' : 'Gemini 스토리보드를 로컬에서 렌더링했어요. 설명의 정확성을 검토해 주세요.';
      $('generated-video-note').textContent = note + ' ' + (data.result?.grounding?.message || '');
      const expires=new Date(data.expires_at*1000).toLocaleString('ko-KR');
      $('video-job-retention').textContent=`보관 만료: ${expires}. 삭제·서버 재시작·쿠키 삭제 시 다시 받을 수 없어요. 필요한 영상은 다운로드해 주세요.`;
    } else clearPlayer();
    if (active) schedule(); else clearTimeout(timer);
  }
  function schedule() { clearTimeout(timer); timer=setTimeout(poll,1000); }
  async function request(url,options={}) {
    const control=new AbortController(), limit=setTimeout(()=>control.abort(),15000);
    try { return await fetch(url,{...options,credentials:'same-origin',cache:'no-store',signal:control.signal}); }
    finally { clearTimeout(limit); }
  }
  async function poll() {
    if (!current) return;
    const id=current, seq=++sequence;
    try {
      const response=await request(`/api/videos/${id}`), data=await response.json();
      if (current!==id) return;
      if (response.status===404) {
        clearPlayer(); setActive(false); remember(null); clearTimeout(timer);
        $('video-job-stage').textContent='이 작업을 복구할 수 없어요';
        error('작업이 만료됐거나 서버가 재시작됐어요. 같은 브라우저의 쿠키가 지워진 경우에도 다시 생성해야 해요.');
        $('video-cancel').hidden=true; $('video-retry').hidden=false; return;
      }
      if (!response.ok) throw Error('status unavailable');
      accept(data,seq);
    } catch {
      if (id!==current) return;
      error('서버와 연결이 끊겼어요. 작업은 서버에서 계속될 수 있어요. 상태를 다시 확인해 주세요.');
      $('video-resume').hidden=false;
      // Keep ownership/ID and retry polling; never silently create another job.
      clearTimeout(timer); timer=setTimeout(poll,5000);
    }
  }
  async function start(body) {
    if (active) { error('진행 중인 영상을 완료하거나 취소한 뒤 다시 생성해 주세요.'); return; }
    clearPlayer(); $('video-job').hidden=false; $('video-job-stage').textContent='영상 생성 요청 중';
    const response=await request('/api/videos',{method:'POST',body}), data=await response.json();
    if (!response.ok) { const e=new Error(typeof data.detail==='string'?data.detail:'영상 요청을 확인해 주세요.'); e.code=data.code || 'video_request_failed'; error(e.message); $('video-retry').hidden=false; $('video-cancel').hidden=true; throw e; }
    if (response.status!==202 || !/^[a-f0-9]{32}$/.test(data.job_id)) throw Error('영상 작업 응답을 확인할 수 없어요.');
    current=data.job_id; remember(current); clearPlayer(); accept(data,++sequence);
    $('video-job').focus({preventScroll:true}); $('video-job').scrollIntoView({behavior:'smooth',block:'start'});
  }
  async function cancel() {
    if (!current) return;
    const id=current, seq=++sequence;
    $('video-cancel').disabled=true; $('video-delete').disabled=true;
    try {
      const response=await request(`/api/videos/${id}`,{method:'DELETE'}),data=await response.json();
      if (!response.ok) { await poll(); return; }
      accept(data,seq);
    } catch { error('취소 요청을 확인하지 못했어요. 상태를 다시 확인해 주세요.'); $('video-resume').hidden=false; $('video-cancel').disabled=false; $('video-delete').disabled=false; }
  }
  $('video-cancel').addEventListener('click',cancel); $('video-delete').addEventListener('click',cancel);
  $('video-resume').addEventListener('click',poll);
  $('video-sample').addEventListener('click',()=>window.dispatchEvent(new Event('aha:sample-video')));
  $('shorts-sample').addEventListener('click',()=>window.dispatchEvent(new Event('aha:sample-video')));
  $('video-retry').addEventListener('click',()=>{
    const radio=document.querySelector('[name=format][value=shorts]'); radio.checked=true; radio.dispatchEvent(new Event('change'));
    $('learn-form').requestSubmit();
  });
  $('generated-video').addEventListener('error',()=>{if(displayedURL)error('영상 파일을 불러오지 못했어요. 만료 여부를 확인하거나 다시 생성해 주세요.');});
  window.AHAVideo=Object.freeze({start,get active(){return active;}});
  try { const id=localStorage.getItem(storageKey); if (/^[a-f0-9]{32}$/.test(id || '')) { current=id; $('video-job').hidden=false; setActive(true); poll(); } } catch {}
})();
