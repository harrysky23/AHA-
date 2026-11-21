/* Owned renderer. Storyboard strings only enter textContent, never code/markup. */
"use strict";
(() => {
const W=968,H=916, colors={violet:'#7b5cf0',yellow:'#ffd23f',pink:'#ff6b9a',blue:'#3b82f6',green:'#16a34a'};
const $=id=>document.getElementById(id), root=$('visual');
let spec, current, fallbacks={}, overflow=[], debug={};
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const ease=x=>1-Math.pow(1-clamp(x,0,1),3);
function parts(text,size=62){
  const out=[];let rest=String(text);
  while(rest.length>size){let cut=rest.lastIndexOf(' ',size);if(cut<size*.45)cut=size;out.push(rest.slice(0,cut));rest=rest.slice(cut).trimStart();}
  if(rest)out.push(rest);return out.length?out:[''];
}
function fit(el,max=34,min=23){
  for(let n=max;n>=min;n--){el.style.fontSize=n+'px';if(el.scrollHeight<=el.clientHeight+1&&el.scrollWidth<=el.clientWidth+1)return true;}
  overflow.push('text_capacity');return false;
}
function box(text,x,y,w,h,{font=32,min=23,bg=null,color=null,weight=null,align='left'}={}){
  const el=document.createElement('div');el.className='box';el.textContent=text;
  Object.assign(el.style,{left:Math.round(x)+'px',top:Math.round(y)+'px',width:Math.round(w)+'px',height:Math.round(h)+'px',textAlign:align});
  if(bg){el.style.background=bg;el.style.padding='16px';}
  if(color)el.style.color=color;if(weight)el.style.fontWeight=weight;
  root.append(el);fit(el,font,min);return el;
}
const NS='http://www.w3.org/2000/svg';
function svg(){const e=document.createElementNS(NS,'svg');e.setAttribute('viewBox',`0 0 ${W} ${H}`);root.append(e);return e;}
function shape(parent,tag,attrs){const e=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,String(v));parent.append(e);return e;}
function state(id,t){let visible=true,hi=false,since=null;for(const cue of current.cues){if(cue.at_seconds>t)break;if(cue.target_id!==id)continue;
  if(cue.action==='hide')visible=false;if(cue.action==='reveal'){visible=true;since=cue.at_seconds;}if(cue.action==='highlight'){hi=true;since=cue.at_seconds;}}
  return {visible,hi,since};}
function motion(el,id,t,delay=0){const s=state(id,t);let a=ease((t-delay)/.45);if(s.since!==null)a=ease((t-s.since)/.35);
  el.dataset.elementId=id;
  el.style.opacity=s.visible?String(a):'0';el.style.transformOrigin='center';
  // No CSS clock: translation, scale and fade depend exclusively on explicit t.
  if(el.namespaceURI!==NS){el.style.top=Math.round(parseFloat(el.style.top)+(1-a)*14)+'px';
    if(s.hi){const scale=1+.025*ease((t-(s.since||0))/.35),w=parseFloat(el.style.width),h=parseFloat(el.style.height);
      el.style.left=Math.round(parseFloat(el.style.left)-w*(scale-1)/2)+'px';el.style.top=Math.round(parseFloat(el.style.top)-h*(scale-1)/2)+'px';el.style.width=Math.round(w*scale)+'px';el.style.height=Math.round(h*scale)+'px';}}
  if(s.hi){el.style.filter='drop-shadow(0 0 7px #ffd23f)';}return el;}
function label(text,x,y,w=220,h=76,font=27){h=Math.max(h,76);return box(text,clamp(x,16,W-w-16),clamp(y,8,H-h-8),w,h,{font,min:22,bg:'#ffffffdf'});}
function markerPoint(v,m,t){let previous={at_seconds:0,point:m.point};let next=null;
  for(const k of v.marker_keyframes.filter(k=>k.marker_id===m.id)){if(k.at_seconds<=t)previous=k;else{next=k;break;}}
  let point={...previous.point};if(next){const f=clamp((t-previous.at_seconds)/(next.at_seconds-previous.at_seconds),0,1);point={x:previous.point.x+(next.point.x-previous.point.x)*f,y:previous.point.y+(next.point.y-previous.point.y)*f};}
  if(m.curve_id){const c=v.curves.find(c=>c.id===m.curve_id);point.y=c.coefficients.reduce((a,b,i)=>a+b*point.x**i,0);}return point;
}
function graph(v,t){
  const chart={x:100,y:120,w:760,h:620},X=x=>chart.x+(x-v.x_range.min)/(v.x_range.max-v.x_range.min)*chart.w,
    Y=y=>chart.y+chart.h-(y-v.y_range.min)/(v.y_range.max-v.y_range.min)*chart.h;
  const s=svg(),defs=shape(s,'defs',{}),clip=shape(defs,'clipPath',{id:'plot-clip'});shape(clip,'rect',{x:chart.x,y:chart.y,width:chart.w,height:chart.h});
  for(let i=0;i<=4;i++){const x=chart.x+chart.w*i/4,y=chart.y+chart.h*i/4;shape(s,'line',{x1:x,x2:x,y1:chart.y,y2:chart.y+chart.h,stroke:'#eee9fa','stroke-width':2});shape(s,'line',{x1:chart.x,x2:chart.x+chart.w,y1:y,y2:y,stroke:'#eee9fa','stroke-width':2});
    box(Number((v.x_range.min+(v.x_range.max-v.x_range.min)*i/4).toFixed(2)).toString(),x-38,chart.y+chart.h+14,76,42,{font:24,min:22,align:'center'});
    box(Number((v.y_range.max-(v.y_range.max-v.y_range.min)*i/4).toFixed(2)).toString(),16,y-20,70,42,{font:24,min:22,align:'right'});}
  box(v.x_label,690,804,230,60,{font:28,min:22,align:'right'});box(v.y_label,42,24,500,60,{font:29,min:22});
  const lines=shape(s,'g',{'clip-path':'url(#plot-clip)'});
  for(const c of v.curves){const points=[];for(let i=0;i<=240;i++){const x=v.x_range.min+(v.x_range.max-v.x_range.min)*i/240;const y=c.coefficients.reduce((a,b,p)=>a+b*x**p,0);points.push(`${X(x)},${clamp(Y(y),-1e8,1e8)}`);}
    motion(shape(lines,'polyline',{points:points.join(' '),fill:'none',stroke:colors[c.color],'stroke-width':7}),c.id,t);}
  const positions=Object.fromEntries(v.markers.map(m=>[m.id,markerPoint(v,m,t)]));debug.markers=positions;
  for(const c of v.connectors){const a=positions[c.start_marker],b=positions[c.end_marker];let x1=X(a.x),y1=Y(a.y),x2=X(b.x),y2=Y(b.y);const dx=x2-x1,dy=y2-y1;
    if(Math.hypot(dx,dy)<1e-8)continue;if(c.extend){const scale=2000/Math.hypot(dx,dy);x1-=dx*scale;y1-=dy*scale;x2+=dx*scale;y2+=dy*scale;}
    motion(shape(lines,'line',{x1,y1,x2,y2,stroke:colors[c.color],'stroke-width':5,'stroke-dasharray':c.id==='tangent'?'14 9':'none'}),c.id,t);}
  // Marker names + current coordinates are in a fixed legend, avoiding collisions
  // when secant points converge. Moving circles remain clipped to the plot.
  for(const m of v.markers){const p=positions[m.id];motion(shape(lines,'circle',{cx:X(p.x),cy:Y(p.y),r:11,fill:colors[m.color],stroke:'white','stroke-width':3}),m.id,t);}
  const legend=[...v.curves,...v.connectors].map(c=>({id:c.id,text:c.label,color:colors[c.color]}));
  legend.forEach((l,i)=>motion(box(l.text,120+(i%3)*258,64+Math.floor(i/3)*44,250,44,{font:24,min:22,color:l.color,weight:800}),l.id,t));
  const mtext=v.markers.map(m=>{const p=positions[m.id],name=m.label.replace(/\([^)]*\)/g,'').trim();return `${name} (${p.x.toFixed(2)}, ${p.y.toFixed(2)})`;}).join('   ');
  box(mtext,80,858,820,42,{font:23,min:22,align:'center'});
}
function nodeLayout(v){const rects=v.nodes.map(n=>({x:clamp(n.x*W-155,20,W-330),y:clamp(n.y*H-95,20,H-210),w:310,h:190}));
  for(let i=0;i<rects.length;i++)for(let j=0;j<i;j++){const a=rects[i],b=rects[j];if(a.x<b.x+b.w+12&&a.x+a.w+12>b.x&&a.y<b.y+b.h+12&&a.y+a.h+12>b.y)throw Error('overlapping_nodes');}return rects;}
function arrow(s,a,b,id,t,halfWidth=155,halfHeight=95){const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy),u={x:dx/d,y:dy/d};
  const padding=Math.min((halfWidth+12)/Math.max(Math.abs(u.x),1e-8),(halfHeight+12)/Math.max(Math.abs(u.y),1e-8),d/2-10);
  const p={x:a.x+u.x*padding,y:a.y+u.y*padding},q={x:b.x-u.x*padding,y:b.y-u.y*padding};
  const g=shape(s,'g',{});shape(g,'line',{x1:p.x,y1:p.y,x2:q.x,y2:q.y,stroke:'#a394c7','stroke-width':5});
  shape(g,'path',{d:`M ${q.x} ${q.y} L ${q.x-u.x*19-u.y*9} ${q.y-u.y*19+u.x*9} L ${q.x-u.x*19+u.y*9} ${q.y-u.y*19-u.x*9} Z`,fill:'#a394c7'});
  const f=(t*.28)%1;shape(g,'circle',{cx:p.x+(q.x-p.x)*f,cy:p.y+(q.y-p.y)*f,r:8,fill:colors.yellow});motion(g,id,t);return {x:(a.x+b.x)/2,y:(a.y+b.y)/2};}
function process(v,t){const rects=nodeLayout(v),s=svg(),map=Object.fromEntries(v.nodes.map((n,i)=>[n.id,{x:rects[i].x+155,y:rects[i].y+95}]));
  for(const e of v.edges){const p=arrow(s,map[e.source],map[e.target],e.id,t);motion(label(e.label,p.x-90,p.y-30,180,60,25),e.id,t);}
  v.nodes.forEach((n,i)=>{const r=rects[i],el=box('',r.x,r.y,r.w,r.h);el.classList.add('node');el.style.borderColor=colors[n.color];
    const a=document.createElement('strong'),b=document.createElement('span');a.textContent=n.label;b.textContent=n.detail;el.append(a,b);
    if(a.scrollHeight>80||b.scrollHeight>95)throw Error('dense_node_text');motion(el,n.id,t,i*.1);});}
function timeline(v,t){const top=100,bottom=806,min=v.events[0].position,max=v.events.at(-1).position;
  const ys=v.events.map(e=>top+(e.position-min)/(max-min)*(bottom-top));if(ys.some((y,i)=>i&&y-ys[i-1]<85))throw Error('dense_timeline');
  const s=svg();shape(s,'line',{x1:215,x2:215,y1:top,y2:bottom,stroke:'#ded4fa','stroke-width':8});
  v.events.forEach((e,i)=>{const y=ys[i],h=Math.min(150,(i+1<ys.length?ys[i+1]-y:170)-16);motion(shape(s,'circle',{cx:215,cy:y,r:15,fill:colors.violet}),e.id,t,i*.15);
    motion(box(e.time_label,24,y-20,162,60,{font:28,min:22,align:'right'}),e.id,t,i*.15);
    motion(box(e.title+'\n'+e.detail,264,y-25,650,h,{font:31,min:23}),e.id,t,i*.15);});}
function compare(v,t){box(v.left_title,40,50,420,100,{font:36,min:24,bg:'#eee8ff',weight:800,align:'center'});box(v.right_title,508,50,420,100,{font:36,min:24,bg:'#fff2cf',weight:800,align:'center'});
  const h=680/v.rows.length;v.rows.forEach((r,i)=>{const y=180+i*h;motion(box(r.aspect,40,y,888,45,{font:25,min:22,weight:800,color:'#837692',align:'center'}),r.id,t);
    motion(box(r.left,40,y+52,420,h-70,{font:32,min:23,bg:r.emphasis==='left'?'#e5dbff':'#f7f4fd'}),r.id,t);
    motion(box(r.right,508,y+52,420,h-70,{font:32,min:23,bg:r.emphasis==='right'?'#fff0b3':'#faf8f0'}),r.id,t);});}
function transition(v,t){let step=v.steps[0];for(const k of v.steps)if(k.at_seconds<=t)step=k;const s=v.states.find(s=>s.id===step.state_id);debug.state_id=s.id;
  // Overview honors declared normalized state positions; current data is shown
  // below it so array cells never compete with state/edge labels.
  const drawing=svg(),centers=Object.fromEntries(v.states.map(n=>[n.id,{x:clamp(n.x*W,140,W-140),y:clamp(n.y*330+60,60,390)}]));
  const rects=v.states.map(n=>({x:centers[n.id].x-120,y:centers[n.id].y-33,w:240,h:66}));
  for(let i=0;i<rects.length;i++)for(let j=0;j<i;j++){const a=rects[i],b=rects[j];if(a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h+10&&a.y+a.h+10>b.y)throw Error('dense_states');}
  for(const e of v.transitions){const p=arrow(drawing,centers[e.source],centers[e.target],e.id,t,120,33);motion(label(e.label,p.x+150,p.y-38,200,76,24),e.id,t);}
  for(const n of v.states){const p=centers[n.id];motion(box(n.label,p.x-120,p.y-33,240,66,{font:27,min:22,bg:n.id===s.id?colors[n.color]:'#f1edf7',color:n.id===s.id?'white':'#8a7d9f',align:'center'}),n.id,t);}
  box(s.detail,56,430,856,110,{font:34,min:25,weight:700,align:'center'});
  const cols=Math.min(8,s.items.length||1),rows=Math.ceil(s.items.length/cols),cellW=840/cols;
  s.items.forEach((item,i)=>{const active=!s.active_range||(i>=s.active_range.low&&i<=s.active_range.high),hi=s.highlight_indices.includes(i);
    const el=box(item,64+(i%cols)*cellW,580+Math.floor(i/cols)*100,cellW-8,84,{font:34,min:22,bg:hi?'#ffd23f':'#eee8ff',align:'center',weight:800});el.style.opacity=active?'1':'.24';});
  box(step.caption,56,rows>1?810:730,856,96,{font:31,min:23,align:'center',color:colors.violet});}
function collect(v){switch(v.type){case'function_graph':return [v.x_label,v.y_label,...v.curves.map(c=>c.label),...v.connectors.map(c=>c.label)];case'process_diagram':return v.nodes.map(n=>n.label+' · '+n.detail);case'timeline':return v.events.map(e=>e.time_label+' · '+e.title+' · '+e.detail);case'comparison':return v.rows.map(r=>r.aspect+'\n'+v.left_title+': '+r.left+'\n'+v.right_title+': '+r.right);case'state_transition':return v.steps.map(k=>k.caption);default:return v.paragraphs||[];}}
function text(v,t,duration){const pages=v.paragraphs.flatMap(p=>parts(p,150)),index=Math.min(pages.length-1,Math.floor(t/duration*pages.length));
  box(v.heading,60,75,848,165,{font:50,min:28,weight:800,color:colors.violet});
  const alpha=ease((t-(duration/pages.length)*index)/.4),el=box(pages[index],60,280,848,480,{font:47,min:29});el.style.opacity=String(alpha);el.style.transform=`translateY(${(1-alpha)*24}px)`;
  box(`${index+1} / ${pages.length}`,60,810,848,48,{font:25,min:23,align:'center',color:'#9b8eae'});}
function draw(scene,t,textMotion=false){current=scene;root.replaceChildren();overflow=[];debug={};let v=scene.visualization;const duration=scene.end_seconds-scene.start_seconds;
  if(textMotion)v={type:'text_explanation',heading:scene.screen.title,paragraphs:[...scene.screen.bullets,...scene.screen.formulas,scene.narration_ko]};
  if(fallbacks[scene.id])v={type:'text_explanation',heading:scene.screen.title,paragraphs:collect(v),fallback_reason:fallbacks[scene.id]};
  try{switch(v.type){case'function_graph':graph(v,t);break;case'process_diagram':process(v,t);break;case'timeline':timeline(v,t);break;case'comparison':compare(v,t);break;case'state_transition':transition(v,t);break;case'text_explanation':text(v,t,duration);break;default:throw Error('unsupported_visualization');}
    if(overflow.length&&v.type!=='text_explanation')throw Error('text_capacity');
  }catch(e){const reasons=['overlapping_nodes','dense_node_text','dense_timeline','dense_states','text_capacity','unsupported_visualization'];
    if(!reasons.includes(e.message))throw Error('renderer_failed');fallbacks[scene.id]=e.message;root.replaceChildren();overflow=[];text({heading:scene.screen.title,paragraphs:collect(scene.visualization)},t,duration);}
  if(fallbacks[scene.id]){const tag=document.createElement('div');tag.className='fallback-tag';tag.textContent='텍스트 설명으로 대체';root.append(tag);}
}
function render(time,options={}){if(!Number.isFinite(time)||time<0||time>spec.duration_seconds)throw Error('invalid_time');
  const scene=spec.scenes.find(s=>time>=s.start_seconds&&time<s.end_seconds)||spec.scenes.at(-1),t=time-scene.start_seconds;
  $('topic').textContent=spec.topic;$('title').textContent=scene.screen.title;fit($('title'),58,32);
  draw(scene,t,options.text_motion===true);
  $('notes').replaceChildren();const formulas=scene.screen.formulas.flatMap(p=>parts(p,24)),bullets=scene.screen.bullets.flatMap(p=>parts(p,60));
  if(formulas.length){const f=document.createElement('div');f.className='formula';f.textContent=formulas[Math.min(formulas.length-1,Math.floor(t/(scene.end_seconds-scene.start_seconds)*formulas.length))];$('notes').append(f);}
  if(bullets.length){const b=document.createElement('div');b.className='bullet';b.textContent=bullets[Math.min(bullets.length-1,Math.floor(t/(scene.end_seconds-scene.start_seconds)*bullets.length))];$('notes').append(b);}
  const chunks=parts(scene.narration_ko,70);let total=chunks.reduce((n,p)=>n+p.length,0),cursor=t/(scene.end_seconds-scene.start_seconds)*total,sub=chunks.at(-1);
  for(const p of chunks){cursor-=p.length;if(cursor<0){sub=p;break;}}$('subtitle').textContent=typeof options.subtitle==='string'?options.subtitle:sub;fit($('subtitle'),39,31);
  const references=scene.source_ids.map(id=>'p.'+spec.sources.find(source=>source.id===id).page).join(', ');
  $('footer').textContent=`${spec.scenes.indexOf(scene)+1} / ${spec.scenes.length}   ·   ${references?'자료 '+references+' · 명세 검토 필요':'설명용 학습 모형 · 명세 검토 필요'}`;
  $('progress').style.width=(time/spec.duration_seconds*1080)+'px';
  return {scene_id:scene.id,type:scene.visualization.type,fallbacks:{...fallbacks},overflow:[...overflow],...debug};
}
window.AHA=Object.freeze({init(value){spec=value;fallbacks={};$('stage').style.zoom=String(innerWidth/1080);
  // Discover layout fallback before frame capture. Stateful animations are
  // sampled at every declared step/keyframe, plus midpoint/end.
  for(const scene of spec.scenes){const d=scene.end_seconds-scene.start_seconds;
    const times=[.8,d/2,d-.001,...(scene.visualization.steps||[]).map(k=>k.at_seconds),...(scene.visualization.marker_keyframes||[]).map(k=>k.at_seconds)];
    for(const t of times)draw(scene,Math.min(t,d));}
  return {fallbacks:{...fallbacks},font:getComputedStyle(document.body).fontFamily};},render,parts});
})();
