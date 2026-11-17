import {readFileSync} from 'node:fs';
import {Script} from 'node:vm';
const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
const js=html.slice(html.indexOf('<script>')+8,html.lastIndexOf('</script>'));
try { new Script(js); } catch(e) { console.error(e.name+': '+e.message); process.exit(1); }
if(!html.includes('<style>:root')||html.includes('<script type="module"'))throw Error('Invalid standalone document');
console.log('STANDALONE_OK: inline stylesheet, JavaScript syntax, no external module entry');
