/* Trusted viewer. Model output is data: text or validated finite geometry. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const visual = $('visual');
  const colors = {violet:'#6541d6', yellow:'#926400', pink:'#be386f', blue:'#236ac0', green:'#148049'};
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(label, action) {
    const node = element('button', label);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  }
  function explorer(labels, describe, groupLabel, navigation = false, onSelect) {
    const list = element('div', undefined, 'choices');
    list.setAttribute('role', 'group');
    list.setAttribute('aria-label', groupLabel);
    const detail = element('div', undefined, 'detail');
    detail.setAttribute('aria-live', 'polite');
    const buttons = labels.map((label, index) => button(label, () => select(index)));
    let selected = 0;
    const previous = button('← 이전 단계', () => select(selected - 1));
    const next = button('다음 단계 →', () => select(selected + 1));
    const progress = element('output', undefined, 'step-progress');
    function select(index) {
      selected = index;
      buttons.forEach((control, i) => control.setAttribute('aria-pressed', String(i === index)));
      detail.replaceChildren(...describe(index));
      onSelect?.(index);
      if (navigation) {
        previous.disabled = index === 0;
        next.disabled = index === buttons.length - 1;
        progress.textContent = `${index + 1} / ${buttons.length} 단계`;
      }
    }
    list.append(...buttons);
    visual.append(list);
    if (navigation && buttons.length > 1) {
      const controls = element('div', undefined, 'movement');
      controls.append(previous, progress, next);
      visual.append(controls);
    }
    visual.append(detail);
    select(0);
  }
  function connections(edges, selected, nodes) {
    const outgoing = edges.filter(edge => edge.source === selected);
    const list = element('ul');
    for (const edge of outgoing) {
      const destination = nodes.find(node => node.id === edge.target);
      list.append(element('li', `${edge.label} → ${destination.label}`));
    }
    return outgoing.length ? [list] : [];
  }
  function process(v, showMap) {
    const selectFlow = showMap ? flowMap(v) : undefined;
    explorer(v.nodes.map(node => node.label), index => {
      const node = v.nodes[index];
      return [element('h3', node.label), element('p', node.detail), ...connections(v.edges, node.id, v.nodes)];
    }, '과정 단계', true, selectFlow);
  }
  function stepExplorer(v) {
    explorer(v.steps.map(step => step.label), index => {
      const step = v.steps[index];
      return [element('h3', step.label), element('p', step.detail)];
    }, '학습 단계', true);
  }
  function timeline(v) {
    explorer(v.events.map(event => event.time_label), index => {
      const event = v.events[index];
      return [element('h3', `${event.time_label} · ${event.title}`), element('p', event.detail)];
    }, '시간 순서');
  }
  function comparison(v) {
    explorer(v.rows.map(row => row.aspect), index => {
      const row = v.rows[index];
      const columns = element('div', undefined, 'columns');
      for (const [title, text] of [[v.left_title, row.left], [v.right_title, row.right]]) {
        const column = element('div');
        column.append(element('h3', title), element('p', text));
        columns.append(column);
      }
      return [element('h3', row.aspect), columns];
    }, '비교 기준');
  }
  function stateTransition(v) {
    explorer(v.steps.map((step, index) => `${index + 1}. ${v.states.find(state => state.id === step.state_id).label}`), index => {
      const step = v.steps[index];
      const state = v.states.find(item => item.id === step.state_id);
      const items = element('div', undefined, 'items');
      state.items.forEach((item, i) => {
        const cell = element('span', item, 'item');
        if (state.active_range && (i < state.active_range.low || i > state.active_range.high)) cell.classList.add('inactive');
        if (state.highlight_indices.includes(i)) cell.classList.add('highlight');
        items.append(cell);
      });
      return [element('h3', state.label), element('p', step.caption), element('p', state.detail), items,
        ...connections(v.transitions, state.id, v.states)];
    }, '상태 변화 단계');
  }
  function explanation(v) {
    visual.append(element('h3', v.heading));
    if (v.paragraphs.length === 1) visual.append(element('p', v.paragraphs[0]));
    else explorer(v.paragraphs.map((_, i) => `설명 ${i + 1}`), i => [element('p', v.paragraphs[i])], '설명 카드');
  }
  function svg(tag, attributes, parent) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    parent.append(node);
    return node;
  }
  function flowMap(v) {
    const scene = svg('svg', {viewBox:'0 0 620 240', class:'process-map', role:'img', 'aria-label':'선택한 단계 사이의 흐름'}, visual);
    const defs = svg('defs', {}, scene);
    const arrow = svg('marker', {id:'flow-arrow', viewBox:'0 0 10 10', refX:8, refY:5, markerWidth:5, markerHeight:5, orient:'auto'}, defs);
    svg('path', {d:'M0 0 10 5 0 10z', fill:'#8473c3'}, arrow);
    const points = new Map(v.nodes.map((node, i) => {
      const theta = i * 2 * Math.PI / v.nodes.length - Math.PI / 2;
      const x = 310 + 240 * Math.cos(theta), y = 120 + 83 * Math.sin(theta);
      return [node.id, {x, y}];
    }));
    const paths = new Map(v.edges.map(edge => {
      const a = points.get(edge.source), b = points.get(edge.target);
      const dx = b.x-a.x, dy = b.y-a.y, distance = Math.hypot(dx,dy);
      const ux = dx/distance, uy = dy/distance;
      const d = `M${a.x+20*ux} ${a.y+20*uy} Q${(a.x+b.x)/2-12*uy} ${(a.y+b.y)/2+12*ux} ${b.x-23*ux} ${b.y-23*uy}`;
      const path = svg('path', {d, 'marker-end':'url(#flow-arrow)', class:'process-route'}, scene);
      return [edge.id, path];
    }));
    const nodes = v.nodes.map((node, index) => {
      const {x,y} = points.get(node.id);
      const group = svg('g', {class:'process-node'}, scene);
      svg('title', {}, group).textContent = node.label;
      svg('circle', {cx:x, cy:y, r:18}, group);
      svg('text', {x,y:y+5,'text-anchor':'middle'}, group).textContent = String(index + 1);
      return group;
    });
    const token = svg('circle', {r:7,class:'process-token'}, scene);
    const controls = element('div', undefined, 'scene-controls');
    const edgeLabel = element('label','흐름 선택');
    edgeLabel.htmlFor = 'flow-edge';
    const edges = element('select');
    edges.id = 'flow-edge';
    const progressLabel = element('label','흐름 움직이기');
    progressLabel.htmlFor = 'flow-progress';
    const progress = element('input');
    progress.type = 'range';
    progress.id = 'flow-progress';
    progress.value = '0';
    controls.append(edgeLabel, edges, progressLabel, progress);
    visual.append(controls);
    function move() {
      const selected = paths.get(edges.value);
      for (const path of paths.values()) path.classList.toggle('active', path === selected);
      token.style.display = selected ? '' : 'none';
      if (!selected) return;
      const point = selected.getPointAtLength(selected.getTotalLength() * Number(progress.value) / 100);
      token.setAttribute('cx', point.x);
      token.setAttribute('cy', point.y);
    }
    progress.addEventListener('input', move);
    edges.addEventListener('change', () => { progress.value = '0'; move(); });
    return (index) => {
      nodes.forEach((node, i) => node.classList.toggle('active', i === index));
      const outgoing = v.edges.filter(edge => edge.source === v.nodes[index].id);
      edges.replaceChildren(...outgoing.map(edge => {
        const destination = v.nodes.find(node => node.id === edge.target);
        const option = element('option', `${edge.label} → ${destination.label}`);
        option.value = edge.id;
        return option;
      }));
      controls.hidden = !outgoing.length;
      progress.value = '0';
      move();
    };
  }
  const evaluate = (curve, x) => curve.coefficients.reduceRight((value, coefficient) => value * x + coefficient, 0);
  const display = (number) => Number(number.toPrecision(5)).toString();
  function pointAt(v, marker, time) {
    const frames = [{at_seconds: 0, point: marker.point}, ...v.marker_keyframes.filter(frame => frame.marker_id === marker.id)];
    const after = frames.findIndex(frame => frame.at_seconds > time);
    if (after < 0) return frames.at(-1).point;
    const a = frames[after - 1], b = frames[after];
    const fraction = (time - a.at_seconds) / (b.at_seconds - a.at_seconds);
    const x = a.point.x + (b.point.x - a.point.x) * fraction;
    const curve = v.curves.find(curve => curve.id === marker.curve_id);
    return {x, y: curve ? evaluate(curve, x) : a.point.y + (b.point.y - a.point.y) * fraction};
  }
  function graph(v) {
    const animated = v.marker_keyframes.length > 0;
    const start = animated ? 0 : v.x_range.min;
    const end = animated ? Math.max(...v.marker_keyframes.map(frame => frame.at_seconds)) : v.x_range.max;
    const xMin = v.x_range.min, xSpan = v.x_range.max - xMin;
    const yMin = v.y_range.min, ySpan = v.y_range.max - yMin;
    const xAt = (x) => 58 + 540 * (x - xMin) / xSpan;
    const yAt = (y) => 292 - 268 * Math.max(-100, Math.min(100, (y - yMin) / ySpan));
    const drawing = svg('svg', {viewBox:'0 0 630 340', role:'img', 'aria-label':`${v.x_label}와 ${v.y_label} 그래프`}, visual);
    const defs = svg('defs', {}, drawing);
    const clip = svg('clipPath', {id:'graph-clip'}, defs);
    svg('rect', {x:58, y:24, width:540, height:268}, clip);
    const plot = svg('g', {'clip-path':'url(#graph-clip)'}, drawing);
    const axes = svg('g', {'font-size':16, fill:'#4c3f67'}, drawing);
    for (let i = 0; i <= 4; i++) {
      const x = 58 + 135 * i, y = 24 + 67 * i;
      svg('line', {x1:x, x2:x, y1:24, y2:292, stroke:'#e3d9f8'}, plot);
      svg('line', {x1:58, x2:598, y1:y, y2:y, stroke:'#e3d9f8'}, plot);
      svg('text', {x, y:317, 'text-anchor':'middle'}, axes).textContent = display(xMin + xSpan * i / 4);
      svg('text', {x:52, y:y+5, 'text-anchor':'end'}, axes).textContent = display(yMin + ySpan * (4-i) / 4);
    }
    for (const curve of v.curves) {
      const points = Array.from({length:161}, (_, i) => {
        const x = xMin + xSpan * i / 160;
        return `${xAt(x)},${yAt(evaluate(curve, x))}`;
      });
      svg('polyline', {points:points.join(' '), fill:'none', stroke:colors[curve.color], 'stroke-width':3}, plot);
    }
    const moving = svg('g', {'clip-path':'url(#graph-clip)'}, drawing);
    const label = element('label', animated ? '점의 이동 조절' : `${v.x_label} 값 조절`);
    label.htmlFor = 'graph-control';
    const slider = element('input');
    slider.id = 'graph-control';
    slider.type = 'range';
    slider.min = '0';
    slider.max = '200';
    slider.value = '0';
    const values = element('div', undefined, 'detail');
    values.setAttribute('aria-live', 'polite');
    const legend = element('div', undefined, 'items');
    for (const line of [...v.curves, ...v.connectors]) {
      const name = element('span', line.label, 'item');
      name.style.color = colors[line.color];
      legend.append(name);
    }
    function render() {
      const value = start + (end - start) * Number(slider.value) / 200;
      const markers = new Map(v.markers.map(marker => [marker.id, pointAt(v, marker, animated ? value : 0)]));
      moving.replaceChildren();
      for (const connector of v.connectors) {
        const a = markers.get(connector.start_marker), b = markers.get(connector.end_marker);
        const ax = xAt(a.x), ay = yAt(a.y), bx = xAt(b.x), by = yAt(b.y);
        const distance = Math.hypot(bx - ax, by - ay);
        if (distance < 1e-9) continue;
        const extension = connector.extend ? 1000 / distance : 0;
        svg('line', {x1:ax-(bx-ax)*extension, y1:ay-(by-ay)*extension,
          x2:bx+(bx-ax)*extension, y2:by+(by-ay)*extension, stroke:colors[connector.color], 'stroke-width':2}, moving);
      }
      const readings = animated
        ? v.markers.map(marker => ({...markers.get(marker.id), label:marker.label, color:marker.color}))
        : v.curves.map(curve => ({x:value, y:evaluate(curve, value), label:curve.label, color:curve.color}));
      for (const point of readings) {
        svg('circle', {cx:xAt(point.x), cy:yAt(point.y), r:5, fill:colors[point.color]}, moving);
      }
      if (!animated) {
        for (const marker of v.markers) {
          const point = markers.get(marker.id);
          svg('circle', {cx:xAt(point.x), cy:yAt(point.y), r:4, fill:colors[marker.color]}, moving);
        }
      }
      slider.setAttribute('aria-valuetext', animated ? `진행 ${Number(slider.value) / 2}%` : display(value));
      values.replaceChildren(...readings.map(point =>
        element('p', `${point.label} · ${v.x_label} ${display(point.x)}, ${v.y_label} ${display(point.y)}`)));
    }
    visual.append(legend, label, slider, values);
    slider.addEventListener('input', render);
    render();
  }
  const renderers = {
    function_graph:graph, process_diagram:process, timeline, comparison,
    state_transition:stateTransition, text_explanation:explanation, step_explorer:stepExplorer,
  };
  function showQuiz(quiz) {
    $('quiz-question').textContent = quiz.question;
    const options = quiz.options.map((option, index) => button(option, () => {
      options.forEach((control, i) => control.setAttribute('aria-pressed', String(index === i)));
      const result = $('quiz-result');
      result.hidden = false;
      result.textContent = index === quiz.correct_index
        ? `정답이에요! ${quiz.explanation}`
        : '다시 생각해 보세요. 실습 내용으로 돌아가 확인할 수 있어요.';
    }));
    options.forEach(control => control.setAttribute('aria-pressed', 'false'));
    $('quiz-options').append(...options);
    $('quiz').hidden = false;
  }
  function showLesson(spec) {
    const renderer = Object.hasOwn(renderers, spec?.visualization?.type) && renderers[spec.visualization.type];
    if (spec?.schema_version !== 'interactive-1' || !renderer) throw new Error('viewer_spec');
    $('lesson-title').textContent = spec.title;
    $('objective').textContent = `학습 목표 · ${spec.objective}`;
    $('explanation').textContent = spec.explanation;
    $('activity').textContent = spec.activity;
    if (spec.visualization.type === 'text_explanation' && spec.visualization.paragraphs.length === 1) {
      $('practice-title').textContent = '개념 설명';
    }
    renderer(spec.visualization, !spec.motion_scene);
    if (spec.motion_scene) {
      $('practice-title').textContent = '직접 움직여 보기';
      $('activity').textContent = '그림 속 대상을 직접 끌거나 슬라이더를 움직여 보세요.';
      const details = element('details', undefined, 'material-steps');
      details.append(element('summary', '학습 자료에 나온 과정'), element('p', spec.activity), ...visual.children);
      window.mountMotionScene(visual, spec.motion_scene, {svg, element, colors});
      visual.append(details);
    }
    if (spec.quiz) showQuiz(spec.quiz);
    const sources = [...spec.source_quotes.map(source => `PDF ${source.page}쪽 · ${source.quote}`), ...spec.limitations];
    $('source-list').append(...sources.map(source => element('li', source)));
    $('sources').hidden = !sources.length;
    $('waiting').hidden = true;
    for (const section of [$('lesson-title').closest('header'), $('practice')]) section.hidden = false;
  }
  function receive(event) {
    if (event.source !== parent || event.data?.type !== 'aha:lesson-spec') return;
    window.removeEventListener('message', receive);
    try {
      showLesson(event.data.spec);
    } catch {
      $('waiting').textContent = '실습을 표시하지 못했어요. 학습 질문을 다시 제출해 주세요.';
    }
  }
  if (parent !== window) {
    window.addEventListener('message', receive);
    new ResizeObserver(([entry]) => {
      if ($('waiting').hidden) {
        parent.postMessage({type:'aha:lesson-size', height:Math.ceil(entry.borderBoxSize[0].blockSize)}, '*');
      }
    }).observe($('content'));
  } else {
    $('waiting').textContent = 'AHA! 학습 화면에서 질문을 입력하면 여기에 실습이 열려요.';
  }
})();
