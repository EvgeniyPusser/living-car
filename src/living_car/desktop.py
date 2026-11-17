"""Native Python/Qt research workbench. VTK actors replay actual MuJoCo states."""
from dataclasses import asdict, replace
from pathlib import Path
import json
import sys
import traceback
import mujoco
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6 import QtCore, QtWidgets
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .body import generate_body
from .brain import owner_configuration
from .schema import Experiment, Genome, Owner, OWNERS, SCENARIOS
from .simulation import Run, compare
from .io import export_pair, load_config, read_pair
from .archive import Archive

ROOT = Path(__file__).resolve().parents[2]
TEAL = "#63ddc4"
STYLE = """
QMainWindow, QWidget { background: #0d131c; color: #d9e2ec; font-family: 'Segoe UI'; font-size: 12px; }
QFrame#header { background: #121c28; border-bottom: 1px solid #283747; }
QLabel#brand { font-size: 25px; font-weight: 700; letter-spacing: 3px; color: #f5f8fb; }
QLabel#eyebrow { color: #71dcc8; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#muted { color: #94a5b8; font-size: 11px; }
QLabel#title { font-size: 21px; font-weight: 600; color: #f1f6fb; }
QLabel#metric { font-size: 22px; font-weight: 600; color: #71dcc8; }
QLabel#warning { background: #2a241b; color: #e5c08b; padding: 9px; border: 1px solid #51432d; border-radius: 5px; }
QGroupBox { border: 1px solid #263546; border-radius: 7px; margin-top: 20px; padding: 12px 9px 9px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; top: 3px; color: #aabacc; }
QPushButton { background: #192738; border: 1px solid #314356; padding: 8px 12px; border-radius: 5px; color: #dce6ef; }
QPushButton:hover { background: #263c50; border-color: #61bba9; }
QPushButton:disabled { color: #5e6e7e; border-color: #26303b; }
QPushButton#primary { background: #69d9c0; color: #09251f; border: none; font-weight: 700; padding: 11px; }
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit { background: #162230; border: 1px solid #314254; border-radius: 4px; padding: 6px; color: #e1eaf2; min-height: 18px; }
QComboBox QAbstractItemView { background: #162230; selection-background-color: #365d60; }
QTabWidget::pane { border: 1px solid #283747; border-radius: 5px; }
QTabBar::tab { background: #121e2b; padding: 9px 12px; border-bottom: 2px solid #121e2b; color: #91a6b8; }
QTabBar::tab:selected { color: #73ddc7; border-bottom: 2px solid #73ddc7; }
QPlainTextEdit { background: #101a26; color: #bbcad9; border: 1px solid #293747; padding: 7px; }
QSlider::groove:horizontal { height: 4px; background: #293b4c; border-radius: 2px; }
QSlider::handle:horizontal { background: #70ddc4; width: 12px; margin: -5px 0; border-radius: 5px; }
QProgressBar { border: 1px solid #314254; border-radius: 3px; text-align: center; height: 14px; }
QProgressBar::chunk { background: #3b8e80; }
QTableWidget { background: #111d29; border: none; gridline-color: #283747; selection-background-color: #294b4c; }
QHeaderView::section { background: #192737; color: #b7c7d7; padding: 7px; border: none; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #111a25; width: 8px; }
QScrollBar::handle:vertical { background: #32475c; border-radius: 4px; min-height: 25px; }
"""

def label(text, kind=None, wrap=False):
    item = QtWidgets.QLabel(text)
    if kind:
        item.setObjectName(kind)
    item.setWordWrap(wrap)
    return item

def text_area(text=""):
    item = QtWidgets.QPlainTextEdit(text)
    item.setReadOnly(True)
    return item

class Worker(QtCore.QThread):
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    def __init__(self, config):
        super().__init__()
        self.config = config
    def run(self):
        try:
            self.completed.emit(compare(self.config))
        except Exception:
            self.failed.emit(traceback.format_exc())

class Workbench(QtWidgets.QMainWindow):
    def __init__(self, replay=None):
        super().__init__()
        self.setWindowTitle("Living Car | Living Things / Cloud DNA")
        self.resize(1520, 960)
        self.setMinimumSize(1150, 760)
        self.config = Experiment()
        self.pair = None
        self.body = None
        self.actors = {}
        self.actor_names = {}
        self.sensor_actors = []
        self.index = 0
        self.playing = False
        self.worker = None
        self.selected_name = "right_1"
        self.profile_path = ROOT / "data" / "local-profile.json"
        self.restore_settings()
        self.setup_ui()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        if replay:
            self.receive(read_pair(replay))
        else:
            QtCore.QTimer.singleShot(150, self.run_experiment)

    def restore_settings(self):
        if self.profile_path.exists():
            try:
                self.config = load_config(json.loads(self.profile_path.read_text(encoding="utf-8")))
            except (ValueError, TypeError, OSError):
                pass

    def save_settings(self):
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(json.dumps(asdict(self.config), indent=2), encoding="utf-8")

    def setup_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(16, 10, 16, 8)
        outer.setSpacing(10)
        header = QtWidgets.QFrame()
        header.setObjectName("header")
        header_layout = QtWidgets.QHBoxLayout(header)
        logo = QtWidgets.QVBoxLayout()
        logo.addWidget(label("LIVING CAR", "brand"))
        logo.addWidget(label("LIVING THINGS / CLOUD DNA", "eyebrow"))
        header_layout.addLayout(logo)
        header_layout.addStretch()
        header_layout.addWidget(label("RESEARCH WORKBENCH    /    01", "eyebrow"))
        header_layout.addSpacing(25)
        self.status = label("INITIALIZING", "muted")
        header_layout.addWidget(self.status)
        outer.addWidget(header)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)
        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(235)
        left_scroll.setMaximumWidth(290)
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(1, 3, 10, 0)
        ll.addWidget(label("EXPERIMENT DESIGN", "eyebrow"))
        ll.addWidget(label("One body.\nMany responses.", "title"))
        ll.addWidget(label("Compare under identical physical conditions. No advantage is assumed.", "muted", True))
        scenario_box = QtWidgets.QGroupBox("01  /  Environment")
        form = QtWidgets.QFormLayout(scenario_box)
        self.scenario = QtWidgets.QComboBox()
        for key, (name, _) in SCENARIOS.items():
            self.scenario.addItem(name, key)
        self.scenario.setCurrentIndex(list(SCENARIOS).index(self.config.scenario))
        self.scenario.currentIndexChanged.connect(self.scenario_changed)
        form.addRow("Scenario", self.scenario)
        self.description = label(SCENARIOS[self.config.scenario][1], "muted", True)
        form.addRow(self.description)
        self.speed = QtWidgets.QDoubleSpinBox()
        self.speed.setRange(.1, 5)
        self.speed.setSingleStep(.1)
        self.speed.setValue(self.config.speed_mps)
        self.speed.setSuffix(" m/s")
        form.addRow("Initial speed", self.speed)
        self.seed = QtWidgets.QSpinBox()
        self.seed.setRange(0, 999999)
        self.seed.setValue(self.config.seed)
        form.addRow("Random seed", self.seed)
        ll.addWidget(scenario_box)
        brain_box = QtWidgets.QGroupBox("02  /  Individual brain")
        bf = QtWidgets.QFormLayout(brain_box)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["Comfort", "Protection", "Adaptive", "Energy Saving", "Experimental"])
        self.mode.setCurrentText(self.config.mode)
        bf.addRow("Behavior", self.mode)
        self.owner = QtWidgets.QComboBox()
        self.owner.addItems([o.name for o in OWNERS] + ["Custom"])
        self.owner.setCurrentIndex(next((i for i, o in enumerate(OWNERS) if o.name == self.config.owner.name), 3))
        bf.addRow("Local owner", self.owner)
        self.height = QtWidgets.QDoubleSpinBox()
        self.height.setRange(1.2, 2.2)
        self.height.setSingleStep(.01)
        self.height.setValue(self.config.owner.height_m)
        self.height.setSuffix(" m")
        bf.addRow("Height", self.height)
        self.comfort = QtWidgets.QDoubleSpinBox()
        self.comfort.setRange(0, 1)
        self.comfort.setSingleStep(.05)
        self.comfort.setValue(self.config.owner.comfort)
        bf.addRow("Comfort", self.comfort)
        self.owner.currentIndexChanged.connect(self.owner_changed)
        bf.addRow(label("Owner profiles stay on this computer. Rule controller; no trained AI yet.", "muted", True))
        ll.addWidget(brain_box)
        resources = QtWidgets.QGroupBox("03  /  Finite resources")
        rf = QtWidgets.QFormLayout(resources)
        self.battery = QtWidgets.QSpinBox()
        self.battery.setRange(0, 50000)
        self.battery.setSingleStep(1000)
        self.battery.setValue(int(self.config.battery_j))
        self.battery.setSuffix(" J")
        rf.addRow("Actuation + repair", self.battery)
        self.material = QtWidgets.QDoubleSpinBox()
        self.material.setRange(0, 100)
        self.material.setValue(self.config.repair_material_g)
        self.material.setSuffix(" g")
        rf.addRow("Repair material", self.material)
        ll.addWidget(resources)
        self.run_button = QtWidgets.QPushButton("RUN PAIRED EXPERIMENT")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_experiment)
        ll.addWidget(self.run_button)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.progress.setTextVisible(False)
        ll.addWidget(self.progress)
        self.export_button = QtWidgets.QPushButton("Export experiment · JSON")
        self.export_button.clicked.connect(self.export_results)
        ll.addWidget(self.export_button)
        import_button = QtWidgets.QPushButton("Open saved replay")
        import_button.clicked.connect(self.import_results)
        ll.addWidget(import_button)
        ll.addStretch()
        ll.addWidget(label("HYPOTHETICAL ARCHITECTURE\nSimplified multibody dynamics.\nNot a validated crash test.", "warning", True))
        left_scroll.setWidget(left)
        splitter.addWidget(left_scroll)

        center = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(center)
        cl.setContentsMargins(5, 0, 5, 0)
        title_row = QtWidgets.QHBoxLayout()
        title_row.addWidget(label("The adaptive body", "title"))
        title_row.addStretch()
        self.architecture = QtWidgets.QComboBox()
        self.architecture.addItems(["Living Car", "Conventional"])
        self.architecture.currentIndexChanged.connect(self.build_scene)
        title_row.addWidget(self.architecture)
        cl.addLayout(title_row)
        view_row = QtWidgets.QHBoxLayout()
        view_row.addWidget(label("VIEW", "eyebrow"))
        self.view_mode = QtWidgets.QComboBox()
        self.view_mode.addItems(["X-ray", "Exterior", "Structure", "Sensors", "Contact loads", "Damage", "Stiffness"])
        self.view_mode.currentIndexChanged.connect(self.update_view)
        view_row.addWidget(self.view_mode)
        view_row.addStretch()
        camera = QtWidgets.QPushButton("Reset camera")
        camera.clicked.connect(self.reset_camera)
        view_row.addWidget(camera)
        cl.addLayout(view_row)
        self.plotter = QtInteractor(center, auto_update=False)
        self.plotter.set_background("#0d1722", top="#1a2b3d")
        self.plotter.enable_trackball_style()
        self.plotter.add_axes(line_width=2, color="#8ea4b7")
        cl.addWidget(self.plotter.interactor, 1)
        cl.addWidget(label("DRAG TO ORBIT   ·   SCROLL TO ZOOM   ·   CLICK A COMPONENT TO INSPECT", "muted"))
        timeline = QtWidgets.QHBoxLayout()
        self.play_button = QtWidgets.QPushButton("▶ Play")
        self.play_button.clicked.connect(self.toggle_play)
        timeline.addWidget(self.play_button)
        reset = QtWidgets.QPushButton("↺ Reset")
        reset.clicked.connect(self.reset_playback)
        timeline.addWidget(reset)
        self.timeline = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 400)
        self.timeline.valueChanged.connect(self.seek)
        timeline.addWidget(self.timeline, 1)
        self.time_label = label("0.00 / 4.00 s", "muted")
        timeline.addWidget(self.time_label)
        self.play_speed = QtWidgets.QComboBox()
        self.play_speed.addItems(["0.25×", "0.5×", "1×", "2×"])
        self.play_speed.setCurrentIndex(2)
        timeline.addWidget(self.play_speed)
        cl.addLayout(timeline)
        self.chart = Figure(figsize=(7, 2), facecolor="#101b28", layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.chart)
        self.canvas.setMinimumHeight(160)
        self.canvas.setMaximumHeight(220)
        cl.addWidget(self.canvas)
        splitter.addWidget(center)

        right_scroll = QtWidgets.QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMinimumWidth(290)
        right_scroll.setMaximumWidth(370)
        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        rl.addWidget(label("TELEMETRY / LIVE REPLAY", "eyebrow"))
        cards = QtWidgets.QHBoxLayout()
        self.force_label = label("0.00 kN", "metric")
        self.damage_label = label("0.0%", "metric")
        for title, value in (("CONTACT FORCE", self.force_label), ("MEAN DAMAGE", self.damage_label)):
            col = QtWidgets.QVBoxLayout()
            col.addWidget(label(title, "muted"))
            col.addWidget(value)
            cards.addLayout(col)
        rl.addLayout(cards)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.inspector = text_area()
        self.tabs.addTab(self.inspector, "Body")
        self.brain_text = text_area()
        self.tabs.addTab(self.brain_text, "Brain")
        self.dna_text = text_area()
        self.tabs.addTab(self.dna_text, "DNA")
        self.model_text = text_area("ESTABLISHED ENGINEERING ANALOGUES\nMass–spring–damper mechanics; rigid-body contacts; passive crush zones.\n\nEXPERIMENTAL / HYPOTHETICAL\nCoordinated retractable shell, changing material response, autonomous repair. No material calibration is claimed.\n\nMODEL\nMuJoCo integrates constrained multibody dynamics at 1 ms. Adjacent panel tendons transmit force. Plastic link references change only after yield.\n\nNOT YET IMPLEMENTED\nNeural/RL training, long-term lifetime model, calibrated deformable materials, real cloud connectivity.\n\nSee docs/MODEL.md for equations and restrictions.")
        self.tabs.addTab(self.model_text, "Model")
        rl.addWidget(self.tabs, 2)
        rl.addWidget(label("PAIRED OUTCOME", "eyebrow"))
        self.table = QtWidgets.QTableWidget(6, 3)
        self.table.setHorizontalHeaderLabels(["Metric", "Conv.", "Living"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(230)
        rl.addWidget(self.table)
        self.verdict = label("Waiting for a paired calculation.", "muted", True)
        rl.addWidget(self.verdict)
        self.log = text_area()
        self.log.setMaximumHeight(130)
        rl.addWidget(self.log)
        right_scroll.setWidget(right)
        splitter.addWidget(right_scroll)
        splitter.setSizes([250, 850, 320])
        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(label("Concept by Evgenii Bogomazov-Pusser · Independent Researcher, Israel", "muted"))
        footer.addStretch()
        footer.addWidget(label("PYTHON / MUJOCO / VTK    •    LOCAL FIRST", "eyebrow"))
        outer.addLayout(footer)

    def scenario_changed(self):
        self.description.setText(SCENARIOS[self.scenario.currentData()][1])
        self.status.setText("INPUT CHANGED · RUN TO APPLY")

    def owner_changed(self, index):
        if index < len(OWNERS):
            self.height.setValue(OWNERS[index].height_m)
            self.comfort.setValue(OWNERS[index].comfort)

    def read_controls(self):
        index = self.owner.currentIndex()
        owner = OWNERS[index] if index < len(OWNERS) else self.config.owner
        owner = replace(owner, height_m=self.height.value(), comfort=self.comfort.value())
        return replace(self.config, scenario=self.scenario.currentData(), speed_mps=self.speed.value(), seed=self.seed.value(),
                       owner=owner, mode=self.mode.currentText(), battery_j=float(self.battery.value()), repair_material_g=self.material.value())

    def run_experiment(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.playing = False
        self.play_button.setText("▶ Play")
        self.config = self.read_controls()
        self.save_settings()
        self.status.setText("CALCULATING BOTH ARCHITECTURES")
        self.run_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.worker = Worker(self.config)
        self.worker.completed.connect(self.receive)
        self.worker.failed.connect(self.failed)
        self.worker.start()

    def failed(self, error):
        self.progress.setRange(0, 1)
        self.run_button.setEnabled(True)
        self.status.setText("CALCULATION FAILED")
        self.log.setPlainText(error)
        QtWidgets.QMessageBox.critical(self, "Experiment failed", error)

    def receive(self, pair):
        self.pair = pair
        self.config = load_config(pair[1].config)
        self.index = 0
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.run_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.status.setText(f"REPRODUCIBLE RUN · SEED {self.config.seed}")
        self.timeline.setRange(0, len(pair[0].frames) - 1)
        self.timeline.setValue(0)
        self.update_comparison()
        self.build_scene()
        self.draw_chart()
        self.log.setPlainText("\n\n".join(f"{d['time_s']:.2f} s  {d['reason']}" for d in pair[1].decisions))
        try:
            with Archive(ROOT / "data" / "experiments.sqlite") as archive:
                archive.save_genome(self.config.genome)
                for run in pair:
                    archive.save_run(run)
        except OSError as exc:
            self.log.appendPlainText(f"Could not save archive: {exc}")

    @property
    def current_run(self):
        return self.pair[1 if self.architecture.currentIndex() == 0 else 0] if self.pair else None

    def build_scene(self):
        run = self.current_run
        if not run:
            return
        self.body = generate_body(load_config(run.config), run.architecture == "Living Car")
        self.plotter.disable_picking()
        self.plotter.clear()
        self.actors.clear()
        self.actor_names.clear()
        self.sensor_actors = []
        m = self.body.model
        for gid in range(m.ngeom):
            name = m.geom(gid).name
            size = m.geom_size[gid]
            if m.geom_type[gid] == mujoco.mjtGeom.mjGEOM_BOX:
                if name == "barrier":
                    # Draw a finite segment of the same infinite-extent-in-test wall for legibility.
                    size = np.minimum(size, [4.5, 3, 2])
                mesh = pv.Cube(center=(0, 0, 0), x_length=2*size[0], y_length=2*size[1], z_length=2*size[2])
            elif m.geom_type[gid] == mujoco.mjtGeom.mjGEOM_CYLINDER:
                mesh = pv.Cylinder(center=(0,0,0), direction=(0,0,1), radius=size[0], height=2*size[1], resolution=32)
            else:
                continue
            color = "#65c6c1"
            if name == "barrier": color = "#aa7843"
            elif name == "floor": color = "#304557"
            elif name == "engine": color = "#dca45c"
            elif name == "passenger_cell": color = "#62dfb9"
            elif name.startswith("wheel"): color = "#202b37"
            actor = self.plotter.add_mesh(mesh, color=color, smooth_shading=True, specular=.25, name=name, pickable=name != "barrier")
            self.actors[gid] = actor
            self.actor_names[id(actor)] = name
        for site_id in range(m.nsite):
            actor = self.plotter.add_mesh(pv.Sphere(radius=.028), color="#c9fa94", name=f"site_{site_id}", pickable=False)
            self.sensor_actors.append(actor)
        # Ground is presentation only: no fictitious road forces are applied by this visual.
        ground = pv.Plane(center=(0,0,.02), direction=(0,0,1), i_size=15, j_size=12, i_resolution=30, j_resolution=24)
        self.plotter.add_mesh(ground, color="#203244", style="wireframe", opacity=.25, pickable=False)
        self.plotter.add_axes(line_width=2, color="#9ab1c4")
        self.plotter.add_text("LIVING CAR" if run.architecture == "Living Car" else "CONVENTIONAL", position="upper_left", font_size=11, color="#a2c8d4", name="scene-label")
        self.plotter.enable_mesh_picking(callback=self.pick, use_actor=True, show=False, left_clicking=True, show_message=False)
        self.reset_camera()
        self.update_view()

    def pick(self, actor):
        name = self.actor_names.get(id(actor)) or getattr(actor, "name", None)
        if name:
            self.selected_name = name
            self.update_frame()

    def reset_camera(self):
        self.plotter.camera_position = [(5.2, -7.1, 5.3), (.1, .05, .65), (0,0,1)]
        self.plotter.camera.view_angle = 35
        self.plotter.render()

    def update_view(self):
        if self.body:
            mode = self.view_mode.currentText()
            for gid, actor in self.actors.items():
                name = self.body.model.geom(gid).name
                actor.prop.style = "wireframe" if mode == "Structure" and name != "barrier" else "surface"
                actor.prop.opacity = .16 if name == "passenger_cell" else (.48 if name.startswith(("right", "left")) and mode in ("X-ray", "Sensors") else 1.)
            for actor in self.sensor_actors:
                actor.visibility = mode == "Sensors"
            self.update_frame()

    def update_frame(self):
        run, body = self.current_run, self.body
        if not run or body is None:
            return
        frame = run.frames[min(self.index, len(run.frames)-1)]
        body.data.qpos[:] = frame["qpos"]
        mujoco.mj_forward(body.model, body.data)
        mode = self.view_mode.currentText()
        for gid, actor in self.actors.items():
            transform = np.eye(4)
            transform[:3,:3] = body.data.geom_xmat[gid].reshape(3,3)
            transform[:3,3] = body.data.geom_xpos[gid]
            actor.user_matrix = transform
            name = body.model.geom(gid).name
            if gid in body.panel_geoms:
                i = body.panel_geoms.index(gid)
                if mode == "Damage":
                    value = frame["damage"][i]
                elif mode == "Contact loads":
                    value = min(1., frame["panel_force_n"][i] / 15000)
                elif mode == "Stiffness":
                    value = (frame["stiffness_npm"][i] - 40000) / 110000
                else:
                    value = 0.
                actor.prop.color = (float(.25 + .7 * value), float(.76 - .5 * value), float(.73 - .5 * value))
                if name == self.selected_name:
                    actor.prop.show_edges = True
                    actor.prop.edge_color = "#e7f7db"
                else:
                    actor.prop.show_edges = False
        for site_id, actor in enumerate(self.sensor_actors):
            actor.position = body.data.site_xpos[site_id]
        self.force_label.setText(f"{frame['force_n']/1000:.2f} kN")
        self.damage_label.setText(f"{np.mean(frame['damage'])*100:.1f}%")
        self.time_label.setText(f"{frame['time_s']:.2f} / {run.frames[-1]['time_s']:.2f} s")
        self.update_inspector(frame)
        ergonomic = owner_configuration(self.config)
        self.brain_text.setPlainText(f"BOUNDED RULE CONTROLLER\n{frame['reason']}\n\nLOCAL OWNER\n{self.config.owner.name} · {self.config.owner.height_m:.2f} m\nSeat rearward target: {ergonomic['seat_rearward_m']*1000:.0f} mm\nSeat height target: {ergonomic['seat_height_m']*1000:.0f} mm\n\nErgonomic targets are not a biomechanical simulation.\n\nENERGY ACCOUNT\nActuation: {frame['actuation_j']:.1f} J\nRepair: {frame['repair_j']:.1f} J\nBudget: {self.config.battery_j:.0f} J\n\nSAFETY ENVELOPE\nActuators ≤ 6 kN; target travel ≤ 80% of elastic yield; protected shell clearance ≤ 120 mm.\n\nNo neural controller or trained policy is claimed.")
        self.dna_text.setPlainText(f"GENERATIVE GENOTYPE\n{self.config.genome.id}\nGeneration {self.config.genome.generation}\nParent {self.config.genome.parent or 'founder'}\n\n" + json.dumps(asdict(self.config.genome), indent=2) + "\n\nGENETIC SEARCH\nRun the Python `evolve` command for actual mutations and held-out Pareto validation.\n\nEGREGOR\nThe `collective` command evaluates transferable damping from local population evidence. Rejected updates remain withheld. No cloud service is connected.")
        if hasattr(self, "time_cursor"):
            self.time_cursor.set_xdata([frame["time_s"], frame["time_s"]])
            self.canvas.draw_idle()
        self.plotter.render()

    def update_inspector(self, frame):
        body = self.body
        name = self.selected_name
        if name in body.panel_names:
            i = body.panel_names.index(name)
            text = (f"SELECTED / {name.upper()}\n\nHypothetical segmented shell\n\nDisplacement: {frame['panel_displacement_m'][i]*1000:.2f} mm\nPermanent set: {frame['plastic_m'][i]*1000:.2f} mm\nContact load: {frame['panel_force_n'][i]/1000:.2f} kN\nLink stiffness: {frame['stiffness_npm'][i]/1000:.1f} kN/m\nDamping: {self.config.genome.panel_damping:.0f} N·s/m\nDamage: {frame['damage'][i]*100:.2f}%\n\nMECHANICAL CONNECTIONS\nPanel → chassis spring/damper\nPanel → adjacent panels via tendon springs\n\nREPAIR\nCoating defects ≤ 20% only. Plastic deformation is not repaired.\nMaterial used: {frame['repair_material_used_g']:.2f} g")
        else:
            text = f"SELECTED / {name.upper()}\n\nActual rigid-body component.\n\nEngine track travel: {frame['engine_travel_m']*1000:.2f} mm\nShell clearance: {frame['clearance_m']*1000:.2f} mm\nCabin acceleration: {frame['acceleration_g']:.3f} g\nMechanical energy: {frame['mechanical_j']:.2f} J\n\nSpring-linked components propagate force through the shared MuJoCo model.\n\nProtected-volume encroachment is a geometric proxy, not an injury criterion."
        self.inspector.setPlainText(text)

    def update_comparison(self):
        a, b = self.pair
        rows = [("Peak force · kN", "peak_contact_force_n", 1000),
                ("Peak cabin · g", "peak_passenger_acceleration_g", 1),
                ("Damage · %", "mean_residual_damage", .01),
                ("Intrusion · mm", "max_protected_intrusion_m", .001),
                ("Energy cost · J", "total_energy_cost_j", 1),
                ("Plastic set · mm", "max_permanent_panel_deformation_m", .001)]
        for i, (title, key, divisor) in enumerate(rows):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(title))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{a.metrics[key]/divisor:.2f}"))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{b.metrics[key]/divisor:.2f}"))
        better = sum(b.metrics[key] < a.metrics[key] - 1e-7 for _, key, _ in rows)
        worse = sum(b.metrics[key] > a.metrics[key] + 1e-7 for _, key, _ in rows)
        self.verdict.setText(f"Living Car: {better} metrics lower, {worse} higher. Equal mass {b.total_mass_kg:.0f} kg. No aggregate safety score; inspect trade-offs.")

    def draw_chart(self):
        self.chart.clear()
        ax = self.chart.add_subplot()
        ax.set_facecolor("#101b28")
        for run, color in zip(self.pair, ("#b3bdca", TEAL)):
            ax.plot([f["time_s"] for f in run.frames], [f["force_n"]/1000 for f in run.frames], color=color, label=run.architecture, linewidth=1.6)
        ax.set_xlabel("Physical time · s", color="#8fa4b8", fontsize=9)
        ax.set_ylabel("Contact · kN", color="#8fa4b8", fontsize=9)
        ax.tick_params(colors="#8fa4b8", labelsize=8)
        ax.grid(alpha=.10)
        for spine in ax.spines.values(): spine.set_color("#2b3f53")
        ax.legend(loc="upper right", facecolor="#101b28", labelcolor="white", frameon=False, fontsize=8)
        self.time_cursor = ax.axvline(0, color="#edbc76", alpha=.65, linewidth=1)
        self.canvas.draw_idle()

    def seek(self, value):
        self.index = value
        self.update_frame()

    def toggle_play(self):
        if not self.pair:
            return
        if self.index >= len(self.current_run.frames)-1:
            self.timeline.setValue(0)
        self.playing = not self.playing
        self.play_button.setText("Ⅱ Pause" if self.playing else "▶ Play")

    def reset_playback(self):
        self.playing = False
        self.play_button.setText("▶ Play")
        self.timeline.setValue(0)

    def tick(self):
        if not self.playing or not self.pair:
            return
        factors = [.25, .5, 1., 2.]
        frames = self.current_run.frames
        target_time = frames[self.index]["time_s"] + .033 * factors[self.play_speed.currentIndex()]
        index = int(np.searchsorted([f["time_s"] for f in frames], target_time))
        self.timeline.setValue(min(index, len(frames)-1))
        if self.index == len(frames)-1:
            self.playing = False
            self.play_button.setText("▶ Play")

    def export_results(self):
        if not self.pair:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export paired experiment", str(ROOT / "results" / "experiment.json"), "JSON (*.json)")
        if path:
            export_pair(path, *self.pair)
            self.status.setText("EXPORTED · OWNER PROFILE EXCLUDED")

    def import_results(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open saved replay", str(ROOT / "results"), "JSON (*.json)")
        if path:
            try:
                self.playing = False
                self.receive(read_pair(path))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                QtWidgets.QMessageBox.warning(self, "Invalid experiment", str(exc))

    def closeEvent(self, event):
        self.playing = False
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait()
        self.plotter.close()
        super().closeEvent(event)

def launch(smoke=False, replay=None):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Workbench(replay=replay)
    window.show()
    if smoke:
        state = {"attempts": 0}
        def verify():
            state["attempts"] += 1
            if window.pair is None:
                if state["attempts"] > 120:
                    print("GUI_SMOKE_FAILED: no experiment result", flush=True)
                    app.exit(1)
                else:
                    QtCore.QTimer.singleShot(500, verify)
                return
            try:
                window.timeline.setValue(len(window.current_run.frames)//3)
                window.view_mode.setCurrentText("Damage")
                window.architecture.setCurrentText("Conventional")
                window.architecture.setCurrentText("Living Car")
                window.view_mode.setCurrentText("X-ray")
                window.toggle_play()
                window.tick()
                window.toggle_play()
                window.selected_name = "right_1"
                window.update_frame()
                out = ROOT / "results" / "desktop-preview.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                window.grab().save(str(out))
                window.plotter.screenshot(str(ROOT / "results" / "body-preview.png"))
                print(f"GUI_SMOKE_OK: replay, architecture switch, views, playback, picking data; screenshot {out}", flush=True)
                QtCore.QTimer.singleShot(250, window.close)
                QtCore.QTimer.singleShot(300, app.quit)
            except Exception:
                traceback.print_exc()
                window.close()
                app.exit(1)
        QtCore.QTimer.singleShot(1000, verify)
    sys.exit(app.exec())
