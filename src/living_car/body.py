"""Generative MuJoCo body. No meshes or downloaded 3D assets are required."""
from dataclasses import dataclass
from xml.etree.ElementTree import Element, SubElement, tostring
import mujoco
import numpy as np
from .schema import Experiment

@dataclass
class Body:
    model: mujoco.MjModel
    data: mujoco.MjData
    panel_names: list[str]
    panel_joints: list[int]
    panel_dofs: list[int]
    panel_qpos: list[int]
    panel_geoms: list[int]
    actuator_ids: list[int]
    barrier: int
    engine_joint: int
    engine_actuator: int

    @property
    def total_mass(self):
        return float(self.model.body_mass.sum())

def generate_body(config: Experiment, adaptive: bool) -> Body:
    g = config.genome
    root = Element("mujoco", model="Living Car")
    SubElement(root, "compiler", angle="radian", autolimits="true")
    option = SubElement(root, "option", timestep=str(config.dt), gravity="0 0 0", integrator="implicitfast", iterations="80", tolerance="1e-10")
    SubElement(option, "flag", energy="enable")
    default = SubElement(root, "default")
    SubElement(default, "geom", friction="0.25 0.005 0.001", solref="0.008 1", solimp="0.95 0.99 0.001", contype="1", conaffinity="2")
    world = SubElement(root, "worldbody")
    frontal = config.scenario in ("frontal", "oblique")
    SubElement(world, "geom", name="barrier", type="box", pos="3.1 0 .75" if frontal else "0 1.35 .75", size=".18 4 .65" if frontal else "8 .18 .65", mass="0", contype="2", conaffinity="1", rgba=".8 .48 .16 1")
    car = SubElement(world, "body", name="chassis", pos="0 -.4 .72")
    SubElement(car, "joint", name="x", type="slide", axis="1 0 0", damping="0")
    SubElement(car, "joint", name="y", type="slide", axis="0 1 0", damping="0")
    SubElement(car, "joint", name="yaw", type="hinge", axis="0 0 1", damping="120")
    # Same total mass and topology for a paired comparison, irrespective of adaptive control.
    SubElement(car, "geom", name="floor", type="box", pos="-.1 0 -.22", size="2.05 .70 .10", mass="850", rgba=".17 .23 .29 1")
    SubElement(car, "geom", name="passenger_cell", type="box", pos="-.25 0 .30", size=".98 .66 .45", mass="350", rgba=".22 .7 .68 .24")
    # Front/rear passive crush zones on compliant prismatic mechanical links.
    for name, x, axis in (("front_crush", 2.05, "-1 0 0"), ("rear_crush", -2.25, "1 0 0")):
        body = SubElement(car, "body", name=name, pos=f"{x} 0 -.02")
        SubElement(body, "joint", name=name, type="slide", axis=axis, range="-.01 .45", stiffness="220000", damping="3500")
        SubElement(body, "geom", name=name, type="box", size=".14 .86 .25", mass="45", rgba=".2 .58 .6 1")
    names = []
    spacing = 3.6 / g.panels_per_side
    for side, sign in (("right", 1), ("left", -1)):
        for i in range(g.panels_per_side):
            name = f"{side}_{i}"
            names.append(name)
            x = -1.8 + spacing * (i + .5)
            panel = SubElement(car, "body", name=name, pos=f"{x} {sign * .92} .02")
            SubElement(panel, "joint", name=name, type="slide", axis=f"0 {-sign} 0", range="-.012 .25", stiffness=str(g.panel_stiffness), damping=str(g.panel_damping))
            SubElement(panel, "geom", name=name, type="box", size=f"{spacing * .47} .055 .27", mass=str(96 / (2 * g.panels_per_side)), rgba=".2 .72 .73 1")
            # Sensor sites are actual body-attached sites, also visualized in desktop mode.
            SubElement(panel, "site", name=f"sensor_{name}", pos=f"0 {sign * .058} .12", size=".023", rgba=".7 1 .5 1")
    engine = SubElement(car, "body", name="engine", pos="1.32 0 .0")
    SubElement(engine, "joint", name="engine_track", type="slide", axis="-.6 0 -.8", range=f"0 {g.engine_travel if adaptive else .06}", stiffness="60000" if adaptive else "210000", damping="2800")
    SubElement(engine, "geom", name="engine", type="box", size=".30 .39 .23", mass="180", rgba=".74 .48 .23 1", contype="0", conaffinity="0")
    # Wheels and suspension: real articulated masses; no tire-road model in this MVP.
    for x in (-1.4, 1.35):
        for sign in (-1, 1):
            wheel = SubElement(car, "body", name=f"wheel_{x}_{sign}", pos=f"{x} {sign * .82} -.30")
            SubElement(wheel, "joint", type="slide", axis="0 0 1", range="-.06 .06", stiffness="32000", damping="1800")
            SubElement(wheel, "geom", name=f"wheel_{x}_{sign}", type="cylinder", size=".32 .12", quat=".7071068 .7071068 0 0", mass="22", rgba=".09 .11 .14 1", contype="0", conaffinity="0")
    tendons = SubElement(root, "tendon")
    for side in ("right", "left"):
        for i in range(g.panels_per_side - 1):
            tendon = SubElement(tendons, "fixed", name=f"couple_{side}_{i}", stiffness=str(g.coupling_stiffness), damping="300", springlength="0")
            SubElement(tendon, "joint", joint=f"{side}_{i}", coef="1")
            SubElement(tendon, "joint", joint=f"{side}_{i+1}", coef="-1")
    acts = SubElement(root, "actuator")
    for name in names:
        SubElement(acts, "motor", name=f"motor_{name}", joint=name, gear="1", ctrllimited="true", ctrlrange="-6000 6000")
    SubElement(acts, "motor", name="motor_engine", joint="engine_track", gear="1", ctrllimited="true", ctrlrange="-4000 4000")
    m = mujoco.MjModel.from_xml_string(tostring(root, encoding="unicode"))
    d = mujoco.MjData(m)
    if config.scenario == "micro_damage":
        vx, vy = 0., 0.
    elif frontal:
        vx, vy = config.speed_mps, .25 * config.speed_mps if config.scenario == "oblique" else 0.
    elif config.scenario == "near_miss":
        vx, vy = .35, .35 * config.speed_mps
    else:
        vx, vy = .35 * config.speed_mps, config.speed_mps
    d.qvel[:2] = (vx, vy)
    mujoco.mj_forward(m, d)
    jid = [m.joint(n).id for n in names]
    return Body(m, d, names, jid, [int(m.jnt_dofadr[j]) for j in jid], [int(m.jnt_qposadr[j]) for j in jid],
                [m.geom(n).id for n in names], [m.actuator(f"motor_{n}").id for n in names],
                m.geom("barrier").id, m.joint("engine_track").id, m.actuator("motor_engine").id)

def panel_clearances(body: Body) -> np.ndarray:
    """World-space barrier distance; no hidden future trajectory is supplied to control."""
    m, d = body.model, body.data
    barrier_pos, half = d.geom_xpos[body.barrier], m.geom_size[body.barrier]
    frontal = half[0] < half[1]
    axis = 0 if frontal else 1
    normal = np.eye(3)[axis]
    edge = barrier_pos[axis] - half[axis]
    distances = []
    for gid in body.panel_geoms:
        rotation = d.geom_xmat[gid].reshape(3, 3)
        extent = float(np.abs(normal @ rotation) @ m.geom_size[gid])
        distances.append(edge - d.geom_xpos[gid, axis] - extent)
    return np.array(distances)
