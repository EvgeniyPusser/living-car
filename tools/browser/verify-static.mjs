import {readFileSync,existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {Script} from 'node:vm';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const html=readFileSync(path.join(root,'index.html'),'utf8');
if(Buffer.byteLength(html)>50000)throw Error('HTML must remain a normal small document');
for(const match of html.matchAll(/(?:src|href)="([^"]+)"/g)){
  const url=match[1];if(url.startsWith('/'))throw Error('Root-absolute URL breaks GitHub repository pages: '+url);
  if(url.startsWith('./')&&url!=='./'&&!existsSync(path.resolve(root,url)))throw Error('Missing local asset: '+url);
}
new Script(readFileSync(path.join(root,'app.js'),'utf8'));
const physics=readFileSync(path.join(root,'assets/physics.js'),'utf8');
new Script(physics);
const worker=JSON.parse(physics.slice('globalThis.LivingCarPhysics = '.length).trim().replace(/;$/,''));
new Script(worker);
for(const file of ['style.css','assets/physics.js','models/side_contact-living.xml','models/side_contact-conventional.xml','models/frontal-living.xml','models/frontal-conventional.xml'])if(!existsSync(path.join(root,file)))throw Error('Missing '+file);
console.log('STATIC_SITE_OK: small HTML, relative URLs, JS syntax, physics binary and all body models.');
