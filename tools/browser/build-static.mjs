// Developer-only rebuild. The published site needs no Node, Python or build step.
import { build } from 'esbuild';
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const source = path.dirname(fileURLToPath(import.meta.url));
const output = path.resolve(source, '../..');
const read = name => readFile(path.join(source, name), 'utf8');
const wasm = await readFile(path.join(source,'node_modules/@mujoco/mujoco/mujoco.wasm'));
const models = {};
for(const scenario of ['side_contact','frontal']) for(const kind of ['living','conventional']) models[`${scenario}-${kind}`]=await read(`public/models/${scenario}-${kind}.xml`);
let worker = await read('simulation-worker.js');
worker = worker.replace("import wasmUrl from '@mujoco/mujoco/mujoco.wasm?url';", '');
worker = worker.replace("loadMujoco({locateFile:name=>name.endsWith('.wasm')?wasmUrl:name})",()=>`loadMujoco({wasmBinary:Uint8Array.from(atob(${JSON.stringify(wasm.toString('base64'))}),c=>c.charCodeAt(0)),locateFile:()=> 'embedded.wasm'})`);
worker = worker.replace(/const get=async\(name\)=>\{[^\n]+?return r\.text\(\);\};/,()=>`const models=${JSON.stringify(models)};const get=async(name)=>models[kind+'-'+name];`);
const workerBundle = await build({stdin:{contents:worker,resolveDir:source,sourcefile:'simulation-worker.js'},bundle:true,write:false,format:'iife',platform:'browser',target:'es2022',minify:true,external:['module'],define:{'import.meta.url':'self.location.href'}});
let app = await read('app.js');
app = app.replace("import './style.css';", '');
app = app.replace("new Worker(new URL('./simulation-worker.js',import.meta.url),{type:'module'})", "new Worker(URL.createObjectURL(new Blob([globalThis.LivingCarPhysics],{type:'text/javascript'})))");
app = app.replaceAll('import.meta.env.BASE_URL', "'./'");
// OrbitControls reads the camera up vector when it is constructed.
app = app.replace('const controls=new OrbitControls', 'camera.up.set(0,0,1);\nconst controls=new OrbitControls');
const appBundle = await build({stdin:{contents:app,resolveDir:source,sourcefile:'app.js'},bundle:true,write:false,format:'iife',platform:'browser',target:'es2022',minify:true});
let html = await read('template.html');
html = html.replace('</head>', '<link rel="stylesheet" href="./style.css"></head>');
html = html.replace('<script type="module" src="/app.js"></script>', '<script defer src="./assets/physics.js"></script><script defer src="./app.js"></script>');
const css = (await read('style.css')).replace(/^@import[^\n]*\r?\n/,'');
await mkdir(path.join(output,'assets'),{recursive:true});
await mkdir(path.join(output,'models'),{recursive:true});
await writeFile(path.join(output,'index.html'),html);
await writeFile(path.join(output,'style.css'),css);
await writeFile(path.join(output,'app.js'),appBundle.outputFiles[0].text);
await writeFile(path.join(output,'assets/physics.js'),'globalThis.LivingCarPhysics = '+JSON.stringify(workerBundle.outputFiles[0].text)+';\n');
await writeFile(path.join(output,'.nojekyll'),'');
for(const scenario of ['side_contact','frontal']) for(const kind of ['living','conventional']) {
  const name=`${scenario}-${kind}.xml`;
  await copyFile(path.join(source,'public/models',name),path.join(output,'models',name));
}
console.log('Built ordinary static site in project root: index.html, style.css, app.js, assets/, models/. No server-side runtime or setup for visitors.');
