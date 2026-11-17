import './style.css';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
let runs=null,architecture=1,index=0,playing=false,view='xray',selected='right_1',lastTime=0,playhead=0;
let settings={scenario:'side_contact',speed:1,mode:'Adaptive',seed:42,damping:1800,battery:12000,material:30,retraction:.1};
try{settings={...settings,...JSON.parse(localStorage.getItem('living-car-inputs')||'{}')};}catch{}
if(!['side_contact','frontal','oblique','near_miss','micro_damage'].includes(settings.scenario))settings.scenario='side_contact';
const titles={side_contact:'Lateral contact',near_miss:'Narrow clearance',frontal:'Frontal impact',oblique:'Oblique impact',micro_damage:'Local repair'};
const worker=new Worker(new URL('./simulation-worker.js',import.meta.url),{type:'module'});
const renderer=new THREE.WebGLRenderer({canvas:$('#scene'),antialias:true,alpha:false});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor('#19272e');
renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.4;
const scene=new THREE.Scene();scene.fog=new THREE.Fog('#19272e',18,45);
const camera=new THREE.PerspectiveCamera(35,1,.05,100);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.minDistance=4;controls.maxDistance=22;controls.maxPolarAngle=Math.PI*.49;
function resetCamera(){camera.up.set(0,0,1);camera.position.set(5.8,-8.4,6);controls.target.set(.1,0,.7);controls.update();}
resetCamera();
scene.add(new THREE.HemisphereLight('#e0ffef','#263237',3));
const light=new THREE.DirectionalLight('#fff4db',4);light.position.set(3,-5,9);scene.add(light);
const backlight=new THREE.DirectionalLight('#7cdac9',2);backlight.position.set(-5,4,4);scene.add(backlight);
const grid=new THREE.GridHelper(28,56,'#40544f','#293e3d');grid.rotation.x=Math.PI/2;grid.position.z=.025;scene.add(grid);
const floor=new THREE.Mesh(new THREE.PlaneGeometry(50,50),new THREE.MeshStandardMaterial({color:'#17262c',roughness:1}));floor.position.z=.01;scene.add(floor);
const vehicle=new THREE.Group();scene.add(vehicle);let meshes=[],sensors=[];
const raycaster=new THREE.Raycaster();let downPoint=null;
renderer.domElement.addEventListener('pointerdown',e=>downPoint=[e.clientX,e.clientY]);
renderer.domElement.addEventListener('pointerup',e=>{if(!downPoint||Math.hypot(e.clientX-downPoint[0],e.clientY-downPoint[1])>6)return;const rect=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);const hit=raycaster.intersectObjects(meshes).find(h=>h.object.userData.name!=='barrier');if(hit){selected=hit.object.userData.name;const opt=[...$('#component').options].find(o=>o.value===selected);if(opt)$('#component').value=selected;updateFrame();}});
const resize=new ResizeObserver(()=>{const b=renderer.domElement.parentElement.getBoundingClientRect();renderer.setSize(b.width,b.height,false);camera.aspect=b.width/b.height;camera.updateProjectionMatrix();drawChart();});resize.observe($('.scene-container'));
function disposeScene(){vehicle.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material])m.dispose();}});vehicle.clear();meshes=[];sensors=[];}
function buildScene(){
  if(!runs)return;disposeScene();const r=runs[architecture];
  r.geometry.forEach((g,i)=>{
    const size=[...g.size];if(g.name==='barrier'){size[0]=Math.min(size[0],4.5);size[1]=Math.min(size[1],3);}
    const geometry=g.type===5?new THREE.CylinderGeometry(size[0],size[0],size[1]*2,32).rotateX(Math.PI/2):new THREE.BoxGeometry(size[0]*2,size[1]*2,size[2]*2);
    const color=g.name==='barrier'?'#96784c':g.name==='floor'?'#4c6466':g.name==='engine'?'#c29c62':g.name.startsWith('wheel')?'#1e292b':'#a0dfcb';
    const material=new THREE.MeshStandardMaterial({color,metalness:g.name.startsWith('wheel')?.1:.35,roughness:.45,transparent:true});
    const mesh=new THREE.Mesh(geometry,material);mesh.userData={name:g.name,gid:i};
    if(g.name==='passenger_cell'){
      const edges=new THREE.LineSegments(new THREE.EdgesGeometry(geometry),new THREE.LineBasicMaterial({color:'#cee9c6',transparent:true,opacity:.7}));mesh.add(edges);
      // A fixed protected-volume cage; it is not an unmodeled deforming mesh.
    }
    if(g.name==='engine'){const edges=new THREE.LineSegments(new THREE.EdgesGeometry(geometry),new THREE.LineBasicMaterial({color:'#ecd3a6',transparent:true,opacity:.5}));mesh.add(edges);}
    if(r.panel_geometry_ids.includes(i)){const s=new THREE.Mesh(new THREE.SphereGeometry(.037,12,8),new THREE.MeshBasicMaterial({color:'#d8f5af'}));s.position.set(0,g.name.startsWith('right')?g.size[1]+.03:-g.size[1]-.03,.13);mesh.add(s);sensors.push(s);}
    vehicle.add(mesh);meshes.push(mesh);
  });
  applyView();updateFrame();
}
function applyView(){
  for(const mesh of meshes){const name=mesh.userData.name,mat=mesh.material;mat.wireframe=view==='structure'&&name!=='barrier';mat.opacity=name==='passenger_cell'?(view==='exterior'?.22:.09):(name==='barrier'?.65:(name.startsWith('right')||name.startsWith('left'))&&(view==='xray'||view==='sensors')?.5:1);mat.depthWrite=mat.opacity>.9;}
  sensors.forEach(s=>s.visible=view==='sensors');
}
const matrix=new THREE.Matrix4();
function updateFrame(){
  if(!runs)return;const r=runs[architecture],f=r.frames[index];
  meshes.forEach((mesh,i)=>{
    const p=f.positions.slice(i*3,i*3+3),a=f.rotations.slice(i*9,i*9+9);
    matrix.set(a[0],a[1],a[2],p[0],a[3],a[4],a[5],p[1],a[6],a[7],a[8],p[2],0,0,0,1);
    mesh.matrixAutoUpdate=false;mesh.matrix.copy(matrix);
    const panel=r.panel_geometry_ids.indexOf(i);
    if(panel>=0){const factor=view==='damage'?f.damage[panel]:view==='loads'?Math.min(1,f.panel_force_n[panel]/18000):0;mesh.material.color.set('#97d6c2').lerp(new THREE.Color('#dc875b'),factor);mesh.material.emissive.set(mesh.userData.name===selected?'#294b3a':'#000000');}
  });
  $('#force').innerHTML=`${(f.force_n/1000).toFixed(2)}<small> kN</small>`;
  $('#damage').innerHTML=`${(f.damage.reduce((a,b)=>a+b)/6*100).toFixed(1)}<small>%</small>`;
  $('#time').textContent=`${f.time_s.toFixed(2)} / 4.00 s`;
  $('#decision').textContent=f.reason;
  $('#energy').textContent=`${(f.actuation_j+f.repair_j).toFixed(0)} J`;
  $('#energy-bar').style.width=`${Math.min(100,(f.actuation_j+f.repair_j)/Math.max(1,r.config.battery)*100)}%`;
  $('#body-state').textContent=architecture?'ADAPTIVE BODY / GENERATION 01':'CONVENTIONAL BODY / PASSIVE';
  const panel=r.panel_names.indexOf(selected);let rows;
  if(panel>=0){rows=[['Displacement',`${(f.panel_displacement_m[panel]*1000).toFixed(1)} mm`],['Permanent set',`${(f.plastic_m[panel]*1000).toFixed(1)} mm`],['Contact load',`${(f.panel_force_n[panel]/1000).toFixed(2)} kN`],['Damage',`${(f.damage[panel]*100).toFixed(1)}%`],['Link stiffness','90 kN/m'],['Neighbor links','Spring + damper']];}
  else if(selected==='engine')rows=[['Track travel',`${(f.engine_travel_m*1000).toFixed(1)} mm`],['Engine mass','180 kg'],['Track bound',architecture?'200 mm':'60 mm'],['Mechanism','Restrained spring/damper']];
  else rows=[['Cabin acceleration',`${f.acceleration_g.toFixed(3)} g`],['Protected volume','Rigid body'],['Mechanical energy',`${f.mechanical_j.toFixed(1)} J`],['Encroachment proxy',`${(r.metrics.max_protected_intrusion_m*1000).toFixed(1)} mm`]];
  $('#component-data').innerHTML=rows.map(([a,b])=>`<dt>${a}</dt><dd>${b}</dd>`).join('');
  $('#selection').innerHTML=`${selected.replaceAll('_',' ').toUpperCase()}<br><small>${panel>=0?'Mechanically coupled shell segment':'Simulated body component'}</small>`;
  $('#timeline').value=index;drawChart();
}
const rows=[['Peak contact · kN','peak_contact_force_n',1000],['Peak cabin · g','peak_passenger_acceleration_g',1],['Residual damage · %','mean_residual_damage',.01],['Permanent set · mm','max_permanent_panel_deformation_m',.001],['Intrusion proxy · mm','max_protected_intrusion_m',.001],['Energy spent · J','total_energy_cost_j',1]];
function outcome(){
  $('#outcomes').innerHTML=rows.map(([n,key,scale])=>`<tr><td>${n}</td><td>${(runs[0].metrics[key]/scale).toFixed(2)}</td><td>${(runs[1].metrics[key]/scale).toFixed(2)}</td></tr>`).join('');
  const better=rows.filter(([,k])=>runs[1].metrics[k]<runs[0].metrics[k]-1e-7).length,worse=rows.filter(([,k])=>runs[1].metrics[k]>runs[0].metrics[k]+1e-7).length;
  $('#verdict').textContent=`Living Car: ${better} measures lower, ${worse} higher. Equal mass ${runs[1].metrics.mass_kg.toFixed(0)} kg. Inspect the trade-offs; there is no aggregate safety score.`;
}
function drawChart(){
  const canvas=$('#chart'),rect=canvas.getBoundingClientRect(),ratio=Math.min(devicePixelRatio,2);if(!rect.width)return;
  canvas.width=rect.width*ratio;canvas.height=rect.height*ratio;const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
  const w=rect.width,h=rect.height,left=33,right=12,top=10,bottom=25,pw=w-left-right,ph=h-top-bottom;
  const key=$('#chart-metric').value,scale=key==='force_n'?1000:key==='damage'?.01:1;
  const val=f=>key==='damage'?f.damage.reduce((a,b)=>a+b)/6/scale:f[key]/scale;
  const max=runs?Math.max(.01,...runs.flatMap(r=>r.frames.map(val)))*1.13:20;
  ctx.font='9px DM Sans,Arial';ctx.lineWidth=1;
  for(let i=0;i<=4;i++){const y=top+ph*i/4;ctx.strokeStyle='#2b3b3b';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillStyle='#78928a';ctx.textAlign='right';ctx.fillText((max*(1-i/4)).toFixed(max<2?2:0),left-8,y+3);}
  for(let i=0;i<=4;i++){const x=left+pw*i/4;ctx.textAlign='center';ctx.fillStyle='#78928a';ctx.fillText(`${i}.0`,x,h-7);}
  if(!runs)return;
  for(let r=0;r<2;r++){ctx.strokeStyle=r?'#a3e9ce':'#95a0a2';ctx.lineWidth=r?2:1.4;ctx.beginPath();runs[r].frames.forEach((f,i)=>{const x=left+f.time_s/4*pw,y=top+ph-val(f)/max*ph;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();}
  const f=runs[architecture].frames[index];ctx.strokeStyle='#b6a37b88';ctx.lineWidth=1;ctx.beginPath();const cx=left+f.time_s/4*pw;ctx.moveTo(cx,top);ctx.lineTo(cx,top+ph);ctx.stroke();
}
function readSettings(){return {...settings,speed:Math.max(.2,Math.min(3,+$('#speed').value)),mode:$('#mode').value,seed:Math.max(0,Math.min(999999,+$('#seed').value||0)),damping:+$('#damping').value,battery:Math.max(0,Math.min(50000,+$('#battery').value||0)),material:Math.max(0,Math.min(100,+$('#material').value||0))};}
function run(){playing=false;$('#play').innerHTML='▶ <span>Play</span>';settings=readSettings();try{localStorage.setItem('living-car-inputs',JSON.stringify(settings));}catch{}$('#run').disabled=true;$('#play').disabled=true;$('#export').disabled=true;$('#loading').classList.remove('hidden');$('#status').textContent='Computing paired experiment';$('#loading-message').textContent='Running both bodies under identical conditions…';$('#experiment-title').textContent=titles[settings.scenario];worker.postMessage({config:settings,base:import.meta.env.BASE_URL});}
worker.onmessage=({data})=>{
  if(data.type==='progress'){$('#loading-message').textContent=data.message;return;}
  if(data.type==='error'){$('#status').textContent='Experiment could not run';$('#loading-message').textContent='Physics failed to initialize. Please reload or use a current Chrome, Edge, Firefox or Safari browser.';$('#loading strong').textContent='Unable to start physics';$('#run').disabled=false;console.error(data.message);return;}
  if(data.type==='result'){runs=data.runs;index=0;playhead=0;$('#loading').classList.add('hidden');$('#run').disabled=false;$('#play').disabled=false;$('#export').disabled=false;$('#status').textContent='Ready · all calculations on your device';$('#engine-version').textContent=`MUJOCO ${runs[0].physics_version} / WEBASSEMBLY`;outcome();buildScene();window.dispatchEvent(new Event('living-car-ready'));}
};
worker.onerror=e=>{$('#status').textContent='Loading error';$('#loading-message').textContent='Unable to load physics. Reload to retry.';console.error(e);};
$('#run').addEventListener('click',run);
$('#play').addEventListener('click',()=>{if(!runs)return;if(index>=400){index=0;playhead=0;}playing=!playing;$('#play').innerHTML=playing?'Ⅱ <span>Pause</span>':'▶ <span>Play</span>';});
$('#reset').addEventListener('click',()=>{playing=false;index=0;playhead=0;$('#play').innerHTML='▶ <span>Play</span>';updateFrame();});
$('#timeline').addEventListener('input',e=>{playing=false;index=+e.target.value;playhead=index*.01;$('#play').innerHTML='▶ <span>Play</span>';updateFrame();});
$$('[data-scenario]').forEach(b=>b.addEventListener('click',()=>{settings.scenario=b.dataset.scenario;$$('[data-scenario]').forEach(x=>x.classList.toggle('active',x===b));run();}));
$$('[data-architecture]').forEach(b=>b.addEventListener('click',()=>{architecture=+b.dataset.architecture;$$('[data-architecture]').forEach(x=>x.classList.toggle('active',x===b));buildScene();}));
$$('[data-view]').forEach(b=>b.addEventListener('click',()=>{view=b.dataset.view;$$('[data-view]').forEach(x=>x.classList.toggle('active',x===b));applyView();updateFrame();}));
$('#camera').addEventListener('click',resetCamera);$('#component').addEventListener('change',e=>{selected=e.target.value;updateFrame();});$('#chart-metric').addEventListener('change',drawChart);
$('#speed').value=settings.speed;$('#mode').value=settings.mode;$('#seed').value=settings.seed;$('#damping').value=settings.damping;$('#battery').value=settings.battery;$('#material').value=settings.material;
function inputsChanged(){$('#speed-value').textContent=`${(+$('#speed').value).toFixed(1)} m/s`;$('#damping-value').textContent=`${$('#damping').value} N·s/m`;if(runs)$('#status').textContent='Inputs changed · Run paired experiment to apply';}
$$('.inputs input,.inputs select').forEach(e=>e.addEventListener('input',inputsChanged));inputsChanged();
$$('[data-scenario]').forEach(b=>b.classList.toggle('active',b.dataset.scenario===settings.scenario));
$('#method-button').addEventListener('click',()=>$('#method').showModal());$('#close-method').addEventListener('click',()=>$('#method').close());$('#method').addEventListener('click',e=>{if(e.target===$('#method'))$('#method').close();});
function toast(t){$('#toast').textContent=t;$('#toast').classList.add('visible');setTimeout(()=>$('#toast').classList.remove('visible'),3000);}
$('#share').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(location.origin+location.pathname);toast('Link copied. Anyone can open it in their browser.');}catch{if(navigator.share)await navigator.share({title:'Living Car',url:location.href});else toast(location.href);}});
$('#export').addEventListener('click',()=>{if(!runs)return;const blob=new Blob([JSON.stringify({schema_version:'web-1',runs,attribution:'Living Things / Cloud DNA — Concept by Evgenii Bogomazov-Pusser'},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`living-car-${settings.scenario}-${settings.seed}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('Both trajectories and initial conditions exported.');});
function animate(time){requestAnimationFrame(animate);const delta=Math.min(.1,(time-lastTime)/1000);lastTime=time;controls.update();if(playing&&runs){playhead=Math.min(4,playhead+delta*+$('#play-speed').value);const next=Math.min(400,Math.round(playhead*100));if(next!==index){index=next;updateFrame();}if(index>=400){playing=false;$('#play').innerHTML='▶ <span>Play</span>';}}renderer.render(scene,camera);}
requestAnimationFrame(animate);run();
