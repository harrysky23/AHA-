// Trusted entry point. Python owns validation, time/disk limits and process cleanup.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {bundle} from '@remotion/bundler';
import {openBrowser,selectComposition,renderFrames,renderStill} from '@remotion/renderer';
import {localAsset,phaseAt} from './src/motion.mjs';

const project=path.dirname(fileURLToPath(import.meta.url));
const work=path.resolve(process.argv[2]);
const config=JSON.parse(fs.readFileSync(path.join(work,'remotion-input.json'),'utf8'));
const props=config.props;
if (!localAsset(props.audio)||!localAsset(props.background)||![3,6,15,24,30].includes(props.fps) && !(Number.isInteger(props.fps)&&props.fps>=1&&props.fps<=30)) throw Error('invalid_input');
if (!fs.existsSync(config.browser)) throw Error('browser_missing');
let blocked=0;const layout=[],audits=[];
const progress=(phase,frames_done=0)=>{
  const time=frames_done/props.fps;
  const scene=phaseAt(props.scenes,time);
  const target=path.join(work,'progress.json'),tmp=target+'.tmp';
  fs.writeFileSync(tmp,JSON.stringify({phase,scene_id:scene?.id,frames_done,frames_total:props.duration*props.fps}));
  fs.renameSync(tmp,target);
};
let browser,stage='bundle';
try {
  progress('browser');
  const serveUrl=await bundle({entryPoint:path.join(project,config.generated?'src/generated-entry.tsx':'src/index.ts'),rootDir:project,outDir:path.join(work,'bundle'),publicDir:path.join(work,'public'),enableCaching:false,
    webpackOverride:conf=>({...conf,context:project,mode:'production',devtool:false,
      resolve:{...conf.resolve,symlinks:false},resolveLoader:{...conf.resolveLoader,symlinks:false}})});
  stage='csp';
  const index=path.join(serveUrl,'index.html');
  const csp="default-src 'none';script-src 'self' 'unsafe-inline';style-src 'unsafe-inline';img-src 'self' data:;media-src 'self';font-src 'self';connect-src 'self';object-src 'none';frame-src 'none';worker-src 'none';base-uri 'none'";
  fs.writeFileSync(index,fs.readFileSync(index,'utf8').replace('<head>',`<head><meta http-equiv="Content-Security-Policy" content="${csp}">`));
  browser=await openBrowser('chrome',{browserExecutable:config.browser,logLevel:'error',
    ...(config.generated ? {chromeMode:'chrome-for-testing'} : {}),chromiumOptions:{flags:{
    'disable-background-networking':true,'disable-component-update':true,'disable-sync':true,'no-first-run':true,
    'disable-gpu':true,'disable-gpu-compositing':true,'disable-skia-runtime-opts':true,'force-color-profile':'srgb'}}});
  // Pinned Remotion 4.0.545 exposes this CDP session on its Page type.
  // Protect every newly created render page BEFORE it navigates to the bundle.
  const newPage=browser.newPage.bind(browser);
  browser.newPage=async options=>{
    const page=await newPage(options),cdp=page._client();
    await cdp.send('Network.enable');
    await cdp.send('Network.setBypassServiceWorker',{bypass:true});
    await cdp.send('Network.setBlockedURLs',{urls:['ws://*','wss://*']});
    cdp.on('Fetch.requestPaused',async event=>{
      let allowed=false;
      try {
        const u=new URL(event.request.url);
        allowed=(u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname)&&!u.username&&!u.password)||u.protocol==='data:'||event.request.url==='about:blank';
      } catch {}
      try {
        if (allowed) await cdp.send('Fetch.continueRequest',{requestId:event.requestId});
        else {blocked++;await cdp.send('Fetch.failRequest',{requestId:event.requestId,errorReason:'BlockedByClient'});}
      } catch { /* Page may already have closed during cancellation. */ }
    });
    await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
    if(config.probe_network) {
      await page.evaluate(()=>fetch('https://aha-network-probe.invalid/').then(()=>false,()=>true));
    }
    if (config.generated) {
      await page.evaluateOnNewDocument(() => {
        addEventListener('error', () => { document.documentElement.dataset.ahaRenderError = '1'; });
        addEventListener('unhandledrejection', () => { document.documentElement.dataset.ahaRenderError = '1'; });
      });
    }
    const close=page.close.bind(page);
    page.close=async(...args)=>{
      try {
        const checked=await page.evaluate(()=>{
          const nodes=[...document.querySelectorAll('[data-safe]')];
          return nodes.map(el=>{const r=el.getBoundingClientRect();return {kind:el.getAttribute('data-safe'),runtime_error:document.documentElement.dataset.ahaRenderError === '1',
            inside:r.left>=-1&&r.top>=-1&&r.right<=1081&&r.bottom<=1921,
            text_fits:el.scrollHeight<=el.clientHeight+1&&el.scrollWidth<=el.clientWidth+1,
            particles:[...document.querySelectorAll('[data-particle]')].slice(0,5).map(p=>({kind:p.getAttribute('data-particle'),x:p.getAttribute('cx'),y:p.getAttribute('cy'),d:p.getAttribute('d')}))};});
        });
        layout.push(...checked);
      } catch {}
      return close(...args);
    };
    return page;
  };
  stage='select';
  const composition=await selectComposition({serveUrl,id:'AhaLearningShort',inputProps:props,puppeteerInstance:browser,logLevel:'error'});
  const options={serveUrl,composition,inputProps:props,puppeteerInstance:browser,logLevel:'error',scale:config.preview?.5:1};
  stage='frames';
  if(config.stills) {
    fs.mkdirSync(path.join(work,'stills'),{recursive:true});
    for(const frame of config.stills) await renderStill({...options,frame,output:path.join(work,'stills',`${frame}.png`),imageFormat:'png',isProduction:false});
  } else {
    await renderFrames({...options,outputDir:path.join(work,'frames'),imageFormat:'jpeg',jpegQuality:92,
      ...(config.generated ? {disableSharedMemoryCapture:true,timeoutInMilliseconds:20000} : {}),
      imageSequencePattern:'frame-[frame].[ext]',concurrency:2,muted:true,
      onFrameUpdate:count=>progress('frames',count)});
  }
  if(config.audit) {
    fs.mkdirSync(path.join(work,'stills'),{recursive:true});
    const frame=Math.round(2.5*props.fps);
    for(const f of [frame,Math.round(4.5*props.fps),Math.round(9*props.fps),Math.round(15*props.fps),Math.round(18.5*props.fps),frame]) {
      const output=path.join(work,'stills',`audit-${audits.length}.png`);
      await renderStill({...options,frame:f,output,imageFormat:'png',isProduction:false});
      audits.push({frame:f,sha256:createHash('sha256').update(fs.readFileSync(output)).digest('hex'),layout:layout.slice(-3)});
    }
    if(audits[0].sha256!==audits.at(-1).sha256||audits[0].sha256===audits[1].sha256||blocked===0) throw Error('audit_failed');
  }
  if(layout.some(x=>!x.inside||!x.text_fits||x.runtime_error)) throw Error('layout_or_runtime_error');
  fs.writeFileSync(path.join(work,'remotion-frame-report.json'),JSON.stringify({version:'4.0.545',layout,blocked_requests:blocked,network_policy:'loopback_only',frame_count:props.duration*props.fps,audit:audits}));
} catch (error) {
  fs.writeFileSync(path.join(work,'remotion-error.json'),JSON.stringify({stage,code:'render_failed'}));
  // No raw exception, text, props, asset path or browser logs in normal output.
  process.exitCode=1;
} finally {
  if(browser) await browser.close({silent:true});
}
