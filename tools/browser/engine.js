// Browser orchestration of the same MuJoCo 4 engine and Python-generated MJCF bodies.
export function simulate(MJ, xml, config, adaptive) {
  const m = MJ.MjModel.from_xml_string(xml);
  const d = new MJ.MjData(m);
  const out = new MJ.DoubleBuffer(6);
  const id = (kind, name) => { const accessor = m[kind==='joint'?'jnt':kind](name); const n=accessor.id; accessor.delete(); return n; };
  try {
    const names=['right_0','right_1','right_2','left_0','left_1','left_2'];
    const joints=names.map(n=>id('joint',n));
    const qa=joints.map(j=>m.jnt_qposadr[j]), va=joints.map(j=>m.jnt_dofadr[j]);
    const ga=names.map(n=>id('geom',n));
    const acts=names.map(n=>id('actuator',`motor_${n}`));
    const eg=id('joint','engine_track'), ea=id('actuator','motor_engine');
    const eq=m.jnt_qposadr[eg], ev=m.jnt_dofadr[eg];
    const barrier=id('geom','barrier');
    const front=['front_crush','rear_crush'].map(n=>id('joint',n));
    const frontP=[0,0];
    let mass=0; for (const v of m.body_mass) mass+=v;
    const frontal=['frontal','oblique'].includes(config.scenario);
    if(config.scenario!=='micro_damage') {
      d.qvel[0]=frontal?config.speed:.35*(config.scenario==='near_miss'?1:config.speed);
      d.qvel[1]=frontal?(config.scenario==='oblique'?.25*config.speed:0):config.speed*(config.scenario==='near_miss'?.35:1);
    }
    for(let i=0;i<6;i++) m.dof_damping[va[i]]=config.damping;
    MJ.mj_forward(m,d);
    const damage=names.map((_,i)=>config.scenario==='micro_damage'?.08+.04*((((config.seed+1)*(i+13)*16807)%2147483647)%1000)/1000:0);
    const plastic=Array(6).fill(0);
    const stiffness=qa.map((_,i)=>m.jnt_stiffness[joints[i]]);
    const geometry=Array.from({length:m.ngeom},(_,i)=>{const a=m.geom(i);const result={name:a.name,size:Array.from(m.geom_size.slice(i*3,i*3+3)),type:m.geom_type[i]};a.delete();return result;});
    let positiveWork=0,netWork=0,repairEnergy=0,plasticEnergy=0,material=0,peakForce=0,peakG=0,impulse=0,intrusion=0,engineMax=0;
    let reason='Ready. Equal mass and initial conditions.';
    const frames=[],decisions=[];
    let prevReason='';
    const energy=()=>{MJ.mj_energyPos(m,d);MJ.mj_energyVel(m,d);return d.energy[0]+d.energy[1];};
    const initialEnergy=energy();
    function clearances(){
      const ax=frontal?0:1, edge=d.geom_xpos[barrier*3+ax]-m.geom_size[barrier*3+ax];
      return ga.map(g=>{
        const r=g*9+ax*3;
        const extent=Math.abs(d.geom_xmat[r])*m.geom_size[g*3]+Math.abs(d.geom_xmat[r+1])*m.geom_size[g*3+1]+Math.abs(d.geom_xmat[r+2])*m.geom_size[g*3+2];
        return edge-d.geom_xpos[g*3+ax]-extent;
      });
    }
    function sample(force,g,panelForce){
      MJ.mj_forward(m,d);
      frames.push({time_s:d.time,qpos:Array.from(d.qpos),positions:Array.from(d.geom_xpos),rotations:Array.from(d.geom_xmat),force_n:force,acceleration_g:g,damage:[...damage],plastic_m:[...plastic],panel_displacement_m:qa.map(q=>d.qpos[q]),panel_force_n:[...panelForce],engine_travel_m:d.qpos[eq],actuation_j:positiveWork,repair_j:repairEnergy,mechanical_j:energy(),reason,clearance_m:Math.min(...clearances()),repair_material_used_g:material});
    }
    sample(0,0,Array(6).fill(0));
    for(let step=0;step<4000;step++){
      const remaining=Math.max(0,config.battery-positiveWork-repairEnergy);
      const clearance=clearances();
      const threatened=clearance.map(v=>v<.38&&d.qvel[frontal?0:1]>.02);
      d.ctrl.fill(0); d.qfrc_applied.fill(0);
      if(adaptive&&remaining>1){
        const gain={'Comfort':.75,'Protection':1,'Adaptive':.9,'Energy Saving':.45,'Experimental':1}[config.mode]??.9;
        if(!frontal){
          for(let i=0;i<6;i++){
            const target=i<3&&threatened[i]&&damage[i]<=.6?Math.min(.8*.035,config.retraction)*gain:0;
            const raw=42000*(target-d.qpos[qa[i]])-800*d.qvel[va[i]];
            const lim=Math.min(6000,remaining/(.001*(Math.abs(d.qvel[va[i]])+.2)));
            d.ctrl[acts[i]]=Math.max(-lim,Math.min(lim,raw));
          }
        }else{
          const target=threatened.some(Boolean)?.20*.65:0;
          d.ctrl[ea]=Math.max(-4000,Math.min(4000,42000*(target-d.qpos[eq])-1200*d.qvel[ev]));
        }
        let worst=0;for(let a=0;a<m.nu;a++)worst+=Math.abs(d.ctrl[a])*(Math.abs(d.actuator_velocity[a])+.2)*.001;
        if(worst>remaining)for(let a=0;a<m.nu;a++)d.ctrl[a]*=remaining/worst;
        reason=threatened.some(Boolean)?(frontal?'Threat detected: restrained engine track activated.':'Threat detected: bounded shell retraction; neighboring links share loads.'):'No approaching threat. Relaxing to the passive shape.';
      }else reason=adaptive?'Energy reserve exhausted. Passive mechanical fallback.':'Passive body: springs, dampers and crush zones.';
      if(reason!==prevReason){decisions.push({time_s:d.time,reason});prevReason=reason;}
      if(config.scenario==='near_miss')d.qfrc_applied[1]=-mass*.65*d.qvel[1];
      const v0=d.qvel[0],v1=d.qvel[1],av=Array.from(d.actuator_velocity);
      MJ.mj_step(m,d);
      let power=0;for(let a=0;a<m.nu;a++)power+=d.actuator_force[a]*.5*(av[a]+d.actuator_velocity[a]);
      netWork+=power*.001;positiveWork+=Math.max(0,power*.001);
      let force=0;const pf=Array(6).fill(0);
      if(d.ncon){
        const contacts=d.contact;
        for(let ci=0;ci<d.ncon;ci++){
          const c=contacts.get(ci);
          if(c.geom1===barrier||c.geom2===barrier){
            MJ.mj_contactForce(m,d,ci,out);
            const f=out.GetView();const value=Math.hypot(f[0],f[1],f[2]);force+=value;
            const p=ga.indexOf(c.geom1===barrier?c.geom2:c.geom1);if(p>=0)pf[p]+=value;
          }
          c.delete();
        }
        contacts.delete();
      }
      const g=Math.hypot(d.qvel[0]-v0,d.qvel[1]-v1)/.001/9.80665;
      peakForce=Math.max(peakForce,force);peakG=Math.max(peakG,g);impulse+=force*.001;
      for(let i=0;i<6;i++){
        const elastic=d.qpos[qa[i]]-plastic[i],excess=Math.max(0,elastic-.035);
        if(excess){plasticEnergy+=.5*stiffness[i]*(elastic*elastic-.035*.035);plastic[i]+=excess;m.qpos_spring[qa[i]]=plastic[i];damage[i]=Math.max(damage[i],Math.min(1,plastic[i]/.16));}
      }
      for(let i=0;i<2;i++){
        const q=m.jnt_qposadr[front[i]],elastic=d.qpos[q]-frontP[i],excess=Math.max(0,elastic-.055);
        if(excess){plasticEnergy+=.5*m.jnt_stiffness[front[i]]*(elastic*elastic-.055*.055);frontP[i]+=excess;m.qpos_spring[q]=frontP[i];}
      }
      if(adaptive&&d.time>1&&force<1){
        const increments=damage.map((v,i)=>v>0&&v<=.2&&plastic[i]<.005?Math.min(v,.018*.001):0);
        const total=increments.reduce((a,b)=>a+b,0);
        if(total){const scale=Math.max(0,Math.min(1,(config.battery-positiveWork-repairEnergy)/(total*16000),(config.material-material)/(total*80)));for(let i=0;i<6;i++)damage[i]-=increments[i]*scale;repairEnergy+=total*scale*16000;material+=total*scale*80;}
      }
      intrusion=Math.max(intrusion,Math.max(...qa.map(q=>d.qpos[q]))-.205,0);
      engineMax=Math.max(engineMax,d.qpos[eq]);
      if((step+1)%10===0)sample(force,g,pf);
    }
    const metrics={peak_contact_force_n:peakForce,peak_passenger_acceleration_g:peakG,mean_residual_damage:damage.reduce((a,b)=>a+b)/6,max_permanent_panel_deformation_m:Math.max(...plastic),max_protected_intrusion_m:intrusion,total_energy_cost_j:positiveWork+repairEnergy,actuation_energy_j:positiveWork,repair_energy_j:repairEnergy,repair_material_used_g:material,contact_impulse_ns:impulse,max_engine_travel_m:engineMax,initial_mechanical_energy_j:initialEnergy,final_mechanical_energy_j:energy(),net_actuator_work_j:netWork,plastic_dissipation_j:plasticEnergy,mass_kg:mass};
    return {architecture:adaptive?'Living Car':'Conventional',model_version:'lc-multibody-0.1-web',physics_version:MJ.mj_versionString(),config,geometry,panel_names:names,panel_geometry_ids:ga,frames,metrics,decisions,limitations:['Rigid multibody panels and reduced link plasticity; no FEM or calibrated crash-test model.','Damage and protected-space encroachment are proxies, not injury or safety ratings.','Hypothetical adaptation and coating repair. Rule controller; no trained AI.']};
  } finally {out.delete();d.delete();m.delete();}
}
