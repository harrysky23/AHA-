// This entry point runs only inside the restricted Linux rendering container.
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {pipeline} from 'node:stream/promises';
import {validate} from './validate.mjs';

const input = '/input';
const work = '/tmp/work';
const project = '/tmp/project';
const source = path.join(project, 'src/GeneratedVisual.tsx');
const fail = (stage, message) => {
  process.stderr.write(JSON.stringify({stage, message}) + '\n');
  process.exit(1);
};
const run = (command, args, stage) => {
  const result = spawnSync(command, args, {stdio: ['ignore', 'ignore', 'ignore'], timeout: 480000});
  if (result.status === 0) return;
  const diagnostic = path.join(work, 'remotion-error.json');
  if (stage === 'render' && fs.existsSync(diagnostic)) {
    const info = JSON.parse(fs.readFileSync(diagnostic, 'utf8'));
    if (['bundle', 'csp', 'select', 'frames'].includes(info.stage)) fail(stage, info.stage);
  }
  fail(stage, result.error?.code === 'ETIMEDOUT' ? 'Stage timed out' : 'Local stage failed');
};
if (process.argv[2] === 'check') {
  if (process.getuid() !== 65532 || !fs.existsSync('/usr/bin/chromium') || fs.existsSync('/var/run/docker.sock')) process.exit(1);
  process.stdout.write('aha-isolated-v1');
} else {
  fs.mkdirSync(work);
  fs.mkdirSync(project);
  fs.cpSync('/opt/aha/src', path.join(project, 'src'), {recursive: true});
  fs.copyFileSync('/opt/aha/render.mjs', path.join(project, 'render.mjs'));
  fs.symlinkSync('/opt/aha/node_modules', path.join(project, 'node_modules'));
  fs.copyFileSync('/opt/aha/isolated/generated-entry.tsx', path.join(project, 'src/generated-entry.tsx'));
  fs.copyFileSync(path.join(input, 'visual.tsx'), source);
  try { validate(source); } catch (e) { fail('validation', e.message); }
  if (process.argv[2] !== 'validate') {
    const config = JSON.parse(fs.readFileSync(path.join(input, 'composition.json'), 'utf8'));
    fs.mkdirSync(path.join(work, 'public'));
    fs.writeFileSync(path.join(work, 'remotion-input.json'), JSON.stringify({
      props: config.props, preview: config.preview, browser: '/usr/bin/chromium', generated: true,
    }));
    run(process.execPath, [path.join(project, 'render.mjs'), work], 'render');
    const frameReport = JSON.parse(fs.readFileSync(path.join(work, 'remotion-frame-report.json'), 'utf8'));
    const frames = fs.readdirSync(path.join(work, 'frames')).filter(name => /^frame-\d+\.jpeg$/.test(name)).sort();
    if (frameReport.blocked_requests || frames.length !== config.props.duration * config.props.fps) fail('render', 'Blocked request or incomplete capture');
    const digits = frames[0].split('.')[0].slice(6).length;
    const output = path.join(work, 'result.mp4');
    run('/usr/bin/ffmpeg', ['-nostdin','-v','error','-y','-framerate',String(config.props.fps),
      '-i',path.join(work,'frames',`frame-%0${digits}d.jpeg`),'-i',path.join(input,'voice.wav'),
      '-map','0:v:0','-map','1:a:0','-vf','scale=out_range=tv,setparams=range=limited',
      '-af','apad','-t',String(config.props.duration),'-c:v','libx264','-threads','2','-preset','veryfast',
      '-pix_fmt','yuv420p','-color_range','tv','-c:a','aac','-ar','48000','-movflags','+faststart',output], 'encode');
    await pipeline(fs.createReadStream(output), process.stdout);
  }
}
