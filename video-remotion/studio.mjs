// Local Studio wrapper for paths such as AHA! which Webpack cannot parse.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';

const project=path.dirname(fileURLToPath(import.meta.url));
if(process.argv[2]==='--child') {
  // Node preserves the lexical symlink path; Webpack must use that same root.
  process.chdir(project);process.cwd=()=>project;
  const cli=path.join(project,'node_modules/@remotion/cli/remotion-cli.js');
  process.argv=[process.execPath,cli,'studio',path.join(project,'src/index.ts'),'--port','3100','--no-open',...process.argv.slice(3)];
  const {Config}=await import('@remotion/cli/config');
  Config.setCachingEnabled(false);
  Config.overrideWebpackConfig(conf=>({...conf,context:project,resolve:{...conf.resolve,symlinks:false},resolveLoader:{...conf.resolveLoader,symlinks:false}}));
  await import(cli);
} else {
  const args=process.argv.slice(2);
  for(let i=0;i<args.length;i++)if(args[i]==='--props'&&args[i+1])args[i+1]=path.resolve(args[i+1]);
  const alias=fs.mkdtempSync(path.join(os.tmpdir(),'aha-studio-'));
  fs.symlinkSync(project,path.join(alias,'project'),'dir');
  const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>['PATH','HOME','TMPDIR','LANG','LC_ALL','AHA_BROWSER_EXECUTABLE'].includes(key)));
  const child=spawn(process.execPath,['--preserve-symlinks','--preserve-symlinks-main',path.join(alias,'project/studio.mjs'),'--child',...args],{env,stdio:'inherit'});
  for(const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>child.kill(signal));
  child.on('exit',code=>{fs.rmSync(alias,{recursive:true,force:true});process.exitCode=code||0;});
}
