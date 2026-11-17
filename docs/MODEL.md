# Physical model and research boundaries

Model: `lc-multibody-0.1`. All inputs and results use SI unless a display explicitly converts units.

## What the experiment asks

Can a mechanically coupled segmented body, using finite-energy bounded adaptation, reduce a damage proxy under identical initial conditions? The baseline has the same body mass, same initial velocity, same panel topology and material parameters. Its active controls and repair are disabled. For the frontal engine experiment the passive mount is stiffer and has a shorter track; that is a stated architectural difference, not an equal-mount control.

The model has no objective that forces the adaptive car to win. Report force, impulse, cabin acceleration, permanent set, damage, energy and protected-volume encroachment separately.

## Constrained multibody mechanics

MuJoCo solves the rigid multibody dynamics with compliant constraint contacts:

`M(q) q̈ + C(q,q̇) = τ_spring + τ_damping + τ_control + J(q)ᵀ f_contact`.

Gravity is zero. The chassis has planar x/y translation and yaw; vertical motion of the entire vehicle is constrained. Wheels have vertical spring/damper joints but no tire-road contact. This is an isolated low-speed body-contact experiment, not a road vehicle dynamics simulator.

The body mass is 1654 kg: floor/chassis 850, protected cell 350, two crush members 90, shell 96, engine 180, four wheel/suspension masses 88. Mass remains constant when panel count changes. For a default genotype, each side has three equal-length rigid panels. Genotype panel counts 2–5 genuinely change topology and degrees of freedom.

Each shell panel has an inward-pointing prismatic joint, spring `k = 90 kN/m`, damping `c = 1.8 kN s/m`, soft joint travel limits from −12 to +250 mm, and a 6 kN-limited actuator. Adjacent panels have tendon springs acting on their relative inward displacement, `F_neighbor = k_c (q_i − q_j)`, with `k_c = 22 kN/m` and tendon damping 300 N s/m. Damage modifies plastic reference positions, so it affects subsequent mechanics rather than only changing a color.

The integration timestep is 1 ms (`implicitfast`); the test suite checks a 0.5 ms refinement. MuJoCo soft constraints are not exact hard stops: small limit penetration is possible. The supported speed range is 0.1–5 m/s. A successful numerical run at higher speed would not validate a high-speed crash model.

## Contact and senses

The barrier is a fixed rigid box with `solref=(0.008, 1)`, `solimp=(0.95, 0.99, 0.001)` and friction `(0.25, 0.005, 0.001)`. The code sums contact-force vector magnitudes from `mj_contactForce` across barrier/vehicle contacts. This is aggregate interface load, not stress at a material point. Impulse integrates that sum in time and should not be confused with a signed resultant force vector.

Body-attached sensor sites are visualized. The controller uses current geometric world-axis barrier clearance, current velocity and local damage; it receives no future trajectory or future collision outcome. This is a simple ideal noiseless proximity sensor model. There is no unreported prediction network.

The narrow-clearance experiment applies the same lateral viscous braking `F_y = −0.65 m v_y` to both architectures. It can prevent a collision in both; the goal there is to observe constrained adaptation, not to manufacture a baseline crash.

## Morphology and control

The shell's actual joint coordinates change under bounded actuator forces. The baseline rules request inward displacement when measured gap is below the genotype's threshold and approach speed exceeds 0.02 m/s. Command targets are capped by the minimum of the genotype limit, 120 mm protected-volume envelope and **80% of the elastic yield displacement**. Response magnitude varies by the chosen mode. A PD law acts against the physical spring and damper; motion costs energy.

The total positive actuator work is debited from the energy budget. Once reserve is exhausted, commands fall back to zero. Neighbors are coupled by real tendons, not synchronized animation. The current controller does not optimize a full future trajectory and is not trained AI. Owner profiles currently generate local ergonomic targets only; their anthropometric preferences are not used to predict injury or control collision physics.

Morphogenesis here means bounded reversible configuration change plus measured irreversible plastic set. Growth, arbitrary topology rewiring during an impact and changes in material phase are not modeled.

## Plasticity, damage and repair

Each shell spring has a permanent reference `p`. At each step, if `q − p > q_y`, a one-dimensional return map sets `p ← q − q_y`. The removed spring energy is booked as plastic dissipation:

`ΔE_plastic = ½ k [(q − p_old)² − (q − p_new)²]`.

The shell damage proxy is at least `min(1, p / 0.16 m)`. Front/rear crush members have a similar map with a 55 mm elastic yield displacement. This is a reduced spring-link model. It has no mesh-resolved stresses, strain-rate calibration, fracture surface, shell buckling or continuum constitutive law.

In the local-repair experiment, seeded coating defects start between 8% and 12% per panel. Repair is eligible only below 20% damage, below 5 mm plastic set and away from active contact. Repair rate is bounded by genotype, available energy and material:

`Δd ≤ repair_rate Δt`, `E_repair = 16000 ΣΔd J`, `material = 80 ΣΔd g`.

These constants are explicitly hypothetical. The process repairs a coating defect proxy; it does not straighten plastically crushed structures, replace major components or heal a broken passenger cell.

## Engine and passenger cell

The engine has 180 kg mass and a prismatic track in the body-local `(-0.6, 0, -0.8)` direction, spring and damper. The adaptive track limit is genotype-dependent (maximum 220 mm); the baseline has 60 mm and a stiffer mount. An explicit force-limited actuator can pull the engine down and rearward when a frontal threat is detected. The track cannot detach or launch the engine.

Protected-space encroachment is a body-local geometric proxy based on inward shell displacement beyond 205 mm and engine position relative to the rigid cell. The cell itself is rigid. The reported peak cabin acceleration is planar chassis acceleration divided by 9.80665; it is not an occupant injury measure. Actual seatbelts, airbags, human body dynamics, floor bending, obstacle fragmentation and hazards to bystanders are absent. A zero encroachment metric does **not** mean the car is safe.

## Energy accounting

MuJoCo supplies kinetic and conservative potential energy (joint and tendon springs). Net actuator work uses force times midpoint actuator velocity. Positive work alone is charged to the battery; negative work is not credited as recovered battery energy. Repair energy is separately debited. The balance

`E_initial + W_actuator_net − E_final − E_plastic`

is reported as `constraint_damping_numerical_balance_j`. It bundles joint/tendon damping, compliant contact losses, any shared near-miss braking and numerical residuals. It is **not measured heat**. MuJoCo contact softness does not give a calibrated material energy budget. Do not infer exact energy conservation during contact from this residual. The exact conservation test uses isolated passive free translation, where there is no contact, plasticity or control. Timestep refinement also compares contact impulse and damage.

Metrics track every integration step. Exported/visualized samples are normally every 10 steps, so the plotted maximum can be slightly below the recorded full-rate peak.

## Evidence categories

| Category | Meaning in this model |
|---|---|
| Established analogues | Rigid multibody mechanics, damped links, mechanical constraints, passive crush structures, proximity sensing. This does not validate these particular parameters. |
| Experimental analogues | Research into adaptive structures, variable damping and some self-healing coatings. No specific commercial material implementation is claimed here. |
| Hypothetical Living Things mechanisms | A whole coordinated morphing vehicle body, resource-bounded autonomous repair as specified here, generative Cloud DNA and collective transfer of structural strategies. |

## Digital inheritance

Genotype fields create body topology, spring/damping/coupling parameters, yield/travel bounds, sensor thresholds, repair capabilities and controller version. IDs are content hashes. Mutations are reproducible from a NumPy seed; each child stores its parent and incremented generation. Selection is Pareto-based; no arbitrary combined safety score is used.

The first search varies damping, coupling, sensor range and admissible retraction. Since the safety controller can cap travel below the genotype maximum, some mutations are behaviorally neutral. They must not be reported as improvements. Shared experience selects an observed donor's damping parameter; each recipient's compatibility and validation suite are checked. The collective may reject every proposal.

This local demonstrator has no cloud endpoint. Owner profiles are excluded from population records and default exports. Private local settings are kept in an ignored `data/` directory. There is no lifetime-years simulation, neural/RL training or evolutionary proof.

## Dependencies and primary references

- [MuJoCo Python API and installation](https://mujoco.readthedocs.io/en/stable/python.html)
- [MuJoCo computation and constraint model](https://mujoco.readthedocs.io/en/stable/computation/index.html)
- [MuJoCo XML reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html)
- [PyVista documentation](https://docs.pyvista.org/)
- [PyVistaQt usage](https://qtdocs.pyvista.org/usage.html)

The installed environment is recorded in `requirements-tested.txt`; experiment JSON records model and genotype versions, seed, initial conditions and assumptions.
