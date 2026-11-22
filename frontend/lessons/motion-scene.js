/* This renderer makes a draggable model from bounded data and owned SVG shapes. */
(() => {
  'use strict';
  const shapes = {
    circle: 'M0-43a43 43 0 1 1 0 86 43 43 0 1 1 0-86z',
    square: 'M-28-40h56q12 0 12 12v56q0 12-12 12h-56q-12 0-12-12v-56q0-12 12-12z',
    triangle: 'M0-46 46 39h-92z',
    diamond: 'M0-45 45 0 0 45-45 0z',
    drop: 'M0-46C18-23 38-8 38 11a38 38 0 1 1-76 0c0-19 20-34 38-57z',
    cloud: 'M-34 28a19 19 0 1 1 0-38 22 22 0 0 1 41-12 18 18 0 0 1 27 11 20 20 0 0 1-1 39z',
    wave: 'M-49 12c17 0 20-23 37-23s20 23 37 23 15-11 24-11v29H-49z',
    ring: 'M0-43a43 43 0 1 1 0 86 43 43 0 1 1 0-86z M0-26a26 26 0 1 0 0 52 26 26 0 1 0 0-52z',
    arrow: 'M-45-13H6v-24L47 0 6 37V13h-51z',
    spark: 'M0-48 11-13 46-16 19 6 30 42 0 22-30 42-19 6-46-16-11-13z',
    dots: 'M-23 2a14 14 0 1 0 0 28 14 14 0 1 0 0-28z M23 2a14 14 0 1 0 0 28 14 14 0 1 0 0-28z M0-34a14 14 0 1 0 0 28 14 14 0 1 0 0-28z',
    coil: 'M-47 21C-35 21-35-30-22-30S-15 29 0 29 7-30 21-30 31 21 47 21',
    magnet: 'M-36-42h22v42a14 14 0 0 0 28 0v-42h22V0a36 36 0 0 1-72 0z',
    leaf: 'M-34 31C-47-24-5-48 40-38 39 11 19 44-34 31z M-34 31 17-21',
  };
  const width = 640, height = 360;
  const parentWindow = window.parent;
  const point = ({x,y}) => ({x:50+x*(width-100), y:48+y*(height-96)});
  const coordinates = (points) => points.map(({x,y}) => `${x},${y}`).join(' ');
  const mix = (a, b, t) => a + (b-a)*t;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  window.mountMotionScene = (parent, model, {svg, element, colors}) => {
    const scene = svg('svg', {viewBox:`0 0 ${width} ${height}`, class:'motion-scene', role:'img', 'aria-label':model.actor}, parent);
    const defs = svg('defs', {}, scene);
    const dots = svg('pattern', {id:'motion-grid', width:22, height:22, patternUnits:'userSpaceOnUse'}, defs);
    svg('circle', {cx:2,cy:2,r:1.2,fill:'#a18bcf',opacity:.36}, dots);
    const background = svg('image', {width,height, preserveAspectRatio:'xMidYMid slice', 'aria-hidden':'true'}, scene);
    const grid = svg('rect', {width,height, fill:'url(#motion-grid)'}, scene);
    background.addEventListener('load', () => {
      grid.setAttribute('fill', '#f8f5ff');
      grid.setAttribute('fill-opacity', '.20');
    });
    window.addEventListener('message', event => {
      if (event.source !== parentWindow || event.data?.type !== 'aha:motion-background') return;
      const value = event.data.image;
      if (typeof value === 'string' && value.length <= 6_000_000 && /^data:image\/(png|jpeg|webp);base64,/.test(value)) {
        background.setAttribute('href', value);
      }
    });
    const track = model.states.map(point);
    svg('polyline', {points:coordinates(track), class:'motion-track'}, scene);
    const trail = svg('polyline', {class:'motion-trail'}, scene);
    for (const {x,y} of track) svg('circle', {cx:x,cy:y,r:5,class:'motion-point'}, scene);
    function icon(group, pose) {
      const color = colors[pose.color];
      svg('path', {d:shapes[pose.shape], fill:pose.shape === 'coil' ? 'none' : color,
        'fill-rule':'evenodd', 'fill-opacity':.28, stroke:color, 'stroke-width':pose.shape === 'coil' ? 12 : 6,
        'stroke-linecap':'round', 'stroke-linejoin':'round'}, group);
    }
    for (const item of model.landmarks) {
      const {x,y} = point(item);
      const anchor = svg('g', {transform:`translate(${x} ${y})`}, scene);
      svg('title', {}, anchor).textContent = item.label;
      const glyph = svg('g', {transform:`scale(${item.size/80})`}, anchor);
      icon(glyph, item);
      const label = svg('text', {y:clamp(item.size/1.6+20,-y+20,height-y-10), 'text-anchor':'middle', class:'motion-label'}, anchor);
      const letters = Array.from(item.label);
      label.textContent = `${letters.slice(0, 12).join('')}${letters.length > 12 ? '…' : ''}`;
    }
    const actor = svg('g', {class:'motion-actor'}, scene);
    const glow = svg('circle', {r:24, fill:'#fff', stroke:'#6c52c4', 'stroke-width':2}, actor);
    const glyph = svg('g', {}, actor);

    const controls = element('div', undefined, 'scene-controls');
    const label = element('label', `${model.actor} 움직이기`);
    label.htmlFor = 'motion-progress';
    const slider = element('input');
    slider.type = 'range';
    slider.id = 'motion-progress';
    const max = (model.states.length - 1) * 100;
    slider.min = '0';
    slider.max = String(max);
    slider.value = '0';
    controls.append(label, slider, element('small', '개념 모형 · 이동과 변화 관찰'));
    parent.append(controls);

    const stages = element('div', undefined, 'choices');
    stages.setAttribute('role', 'group');
    stages.setAttribute('aria-label', '실습 상태 선택');
    const stateButtons = model.states.map((state, i) => {
      const button = element('button', state.label);
      button.type = 'button';
      button.addEventListener('click', () => seek(i * 100));
      return button;
    });
    stages.append(...stateButtons);
    const detail = element('div', undefined, 'detail');
    detail.setAttribute('aria-live','polite');
    const title = element('h3'), description = element('p');
    detail.append(title,description);
    parent.append(stages,detail);

    let currentStage = -1;
    function seek(value) {
      slider.value = String(Math.round(value));
      const position = Number(slider.value) / 100;
      const start = Math.min(Math.floor(position), track.length-2);
      const end = start+1, ratio = position-start;
      const a = track[start], b = track[end];
      const size = mix(model.states[start].size,model.states[end].size,ratio);
      const positionOnTrack = {x:mix(a.x,b.x,ratio),y:mix(a.y,b.y,ratio)};
      actor.setAttribute('transform', `translate(${positionOnTrack.x} ${positionOnTrack.y})`);
      trail.setAttribute('points', coordinates([...track.slice(0,start+1),positionOnTrack]));
      glyph.setAttribute('transform', `scale(${size/75})`);
      glow.setAttribute('r', size/1.5+8);
      const index = Math.round(position);
      if (index === currentStage) return;
      currentStage = index;
      const state = model.states[index];
      glyph.replaceChildren();
      icon(glyph,state);
      title.textContent = state.label;
      description.textContent = state.detail;
      slider.setAttribute('aria-valuetext',state.label);
      stateButtons.forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
    }

    const hasPath = track.some(p => p.x !== track[0].x || p.y !== track[0].y);
    let drag = null;
    function dragTo(event) {
      const transform = scene.getScreenCTM();
      if (!transform) return;
      const p = new DOMPoint(event.clientX,event.clientY).matrixTransform(transform.inverse());
      if (!hasPath) {
        seek(clamp(drag.position + (p.x - drag.x) * max / width,0,max));
        return;
      }
      const cursorPosition = Number(slider.value);
      const closest = track.slice(1).reduce((best, b, i) => {
        const a = track[i], dx = b.x-a.x, dy = b.y-a.y;
        const length = dx*dx + dy*dy;
        if (length === 0) return best;
        const t = clamp(((p.x-a.x)*dx + (p.y-a.y)*dy)/length,0,1);
        const distance = (p.x-mix(a.x,b.x,t))**2 + (p.y-mix(a.y,b.y,t))**2;
        const position = (i+t)*100;
        const tied = Math.abs(distance-best.distance) < 1;
        const nearer = Math.abs(position-cursorPosition) < Math.abs(best.position-cursorPosition);
        return (tied ? nearer : distance < best.distance) ? {position,distance} : best;
      }, {position:cursorPosition,distance:Infinity});
      seek(closest.position);
    }
    scene.addEventListener('pointerdown', event => {
      if (event.button !== 0 || drag || !scene.getScreenCTM()) return;
      const p = new DOMPoint(event.clientX,event.clientY).matrixTransform(scene.getScreenCTM().inverse());
      drag = {id:event.pointerId,position:Number(slider.value),x:p.x};
      scene.setPointerCapture(event.pointerId);
      dragTo(event);
    });
    scene.addEventListener('pointermove', event => { if (drag?.id === event.pointerId) dragTo(event); });
    scene.addEventListener('lostpointercapture', event => { if (drag?.id === event.pointerId) drag = null; });
    slider.addEventListener('input', () => seek(Number(slider.value)));
    seek(0);
  };
})();
