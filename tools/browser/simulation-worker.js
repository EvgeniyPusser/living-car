import loadMujoco from '@mujoco/mujoco';
import wasmUrl from '@mujoco/mujoco/mujoco.wasm?url';
import {simulate} from './engine.js';
let ready;
self.onmessage=async({data})=>{
  try{
    ready??=loadMujoco({locateFile:name=>name.endsWith('.wasm')?wasmUrl:name});
    const MJ=await ready;
    const config=data.config,kind=['frontal','oblique'].includes(config.scenario)?'frontal':'side_contact';
    self.postMessage({type:'progress',message:'Calculating conventional body…'});
    const get=async(name)=>{const r=await fetch(new URL(`./models/${kind}-${name}.xml`,self.location.origin+data.base));if(!r.ok)throw Error('Body model could not be loaded');return r.text();};
    const [a,b]=await Promise.all([get('conventional'),get('living')]);
    const conventional=simulate(MJ,a,config,false);
    self.postMessage({type:'progress',message:'Calculating adaptive body…'});
    const living=simulate(MJ,b,config,true);
    self.postMessage({type:'result',runs:[conventional,living]});
  }catch(e){self.postMessage({type:'error',message:String(e.stack||e)});}
};
