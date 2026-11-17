# Living Car — first paired experiment

Concept: Evgenii Bogomazov-Pusser · Living Things / Cloud DNA

Scenario: `side_contact`; speed: 1.0 m/s; seed: 42; model: lc-multibody-0.1.
Equal mass: 1654.0 kg. Genotype: `408980bf741b`.

| Metric | Conventional | Living Car | Difference (Living − conventional) |
|---|---:|---:|---:|
| Peak contact force | 15.6342 kN | 19.3963 kN | +3.7622 kN |
| Peak cabin acceleration | 0.9030 g | 1.1791 g | +0.2761 g |
| Residual damage (model fraction) | 0.1216  | 0.0906  | -0.0309  |
| Permanent panel deformation | 38.9539 mm | 29.0016 mm | -9.9522 mm |
| Protected-volume encroachment | 0.0000 mm | 0.0000 mm | +0.0000 mm |
| Energy spent on adaptation + repair | 0.0000 J | 205.3672 J | +205.3672 J |

This is a hypothesis test, not evidence of real automotive safety.

Lower in Living Car: Residual damage (model fraction), Permanent panel deformation.
Higher in Living Car: Peak contact force, Peak cabin acceleration, Energy spent on adaptation + repair.

Damage is a link-plasticity/coating proxy. Contact peaks are solver/timestep dependent.
No single aggregate safety score is assigned. Different metrics may favor different architectures.

## Model limitations

- Planar rigid multibody model; shell deformation is represented by spring-linked panels, not FEM.
- Contact forces are MuJoCo soft-constraint outputs and depend on timestep/contact parameters.
- Plasticity is a reduced return-mapping law on mechanical links; no calibrated automotive material data.
- Protected-cell damage is a clearance/acceleration proxy, not an injury prediction or crash-test rating.
- Adaptive shell and repair mechanisms are hypothetical; this model cannot establish real-world safety.
- No tire-road dynamics, airbag, occupant biomechanics, thermal solver or trained neural controller.
- Constraint and numerical losses are reported together; the energy residual is not measured heat.
