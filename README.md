# tb3_nav_demo: TurtleBot3 + Nav2 in Gazebo Harmonic

A TurtleBot3 Waffle navigates autonomously through a cluttered 7 m × 5 m room, including one
0.9 m wide corridor, using the stock Nav2 stack. No custom navigation code: the robot model,
bridge, localization, planning and control are all existing packages. This repo adds a
world, a map, a parameter file, one launch file and a short goal script.

**Environment:** Ubuntu 24.04 (in distrobox), ROS 2 Jazzy, Gazebo Harmonic (gz-sim 8),
`ros_gz` bridge. Not Gazebo Classic.

**Robot:** TurtleBot3 **Waffle**, from `nav2_minimal_tb3_sim`, the Nav2 maintainers'
minimal TB3 Waffle model for Gazebo Harmonic, which `nav2_bringup` itself depends on.
Chosen over ROBOTIS' `turtlebot3_gazebo` for fewer dependencies and no
`TURTLEBOT3_MODEL` env var. Both are valid.

## Layout

```
tb3_nav_ws/                          repo root = colcon workspace
├── README.md
├── NOTES.md                         build error log + parameter-tuning experiment
├── tools/
│   └── generate_world_and_map.py    one geometry list -> world file + ground-truth map
└── src/tb3_nav_demo/                ament_python package
    ├── launch/demo.launch.py        THE launch file (wraps nav2_bringup tb3_simulation_launch.py)
    ├── worlds/cluttered_room.sdf.xacro
    ├── maps/cluttered_room.{yaml,pgm}
    ├── config/nav2_params.yaml      Jazzy defaults + commented NON-DEFAULT changes
    └── tb3_nav_demo/goal_sequence.py  nav2_simple_commander, 4 sequential goals
```

The world: robot spawns at (-2.0, -0.5) in the cluttered west half. A 1 m thick dividing
wall has a single 0.9 m × 1.0 m corridor at y 0.6–1.5, the only route to the east half.
The robot radius is 0.22 m, so the corridor leaves 0.23 m per side.

## Versions

Recorded with `apt-cache policy` on the build machine (2026-10-26):

| Package | Version |
|---|---|
| ros-jazzy-ros-gz | 1.0.18-1noble.20260126.203319 |
| ros-jazzy-navigation2 | 1.3.10-1noble.20260126.202359 |
| ros-jazzy-nav2-bringup | 1.3.10-1noble.20260126.202428 |
| ros-jazzy-nav2-minimal-tb3-sim | 1.0.1-1noble.20260126.191823 |
| ros-jazzy-nav2-simple-commander | 1.3.10-1noble.20260126.194209 |
| ros-jazzy-slam-toolbox | 2.8.3-1noble.20260126.195907 |
| gz sim | 8.10.0 |

`config/nav2_params.yaml` is based on the `nav2_bringup` 1.3.10 default file. A different
Nav2 version may have different defaults, so check the diff below if you upgrade.

## Setup

Run everything **inside the Jazzy container** (see Troubleshooting for why).

```bash
sudo apt update
sudo apt install -y \
  ros-jazzy-ros-gz ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
  ros-jazzy-nav2-minimal-tb3-sim ros-jazzy-nav2-simple-commander \
  ros-jazzy-slam-toolbox ros-jazzy-teleop-twist-keyboard \
  ros-jazzy-xacro ros-jazzy-robot-state-publisher \
  python3-colcon-common-extensions python3-rosdep

# once per machine
sudo rosdep init 2>/dev/null; rosdep update

git clone https://github.com/ShubhkarmanSingh7/navigation-jazzy.git ~/tb3_nav_ws
cd ~/tb3_nav_ws
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -y
colcon build --symlink-install
source install/setup.bash
```

## Run (one command)

```bash
ros2 launch tb3_nav_demo demo.launch.py
```

This starts Gazebo (world + Waffle + `ros_gz` bridge), Nav2 (map server, AMCL, planner,
MPPI controller, behaviors, BT navigator) and RViz, all with `use_sim_time:=true`.

Optional arguments:

| Argument | Default | Use |
|---|---|---|
| `headless:=True` | `False` | No Gazebo window; RViz still opens. Saves GPU. |
| `slam:=True` | `False` | slam_toolbox builds a map instead of AMCL + saved map (**untested**) |
| `autostart:=false` | `true` | Sim + RViz only; Nav2 loads but stays inactive |
| `params_file:=...` | package config | Alternate Nav2 params (tuning experiments) |

## Initial pose

**Automatic (default).** AMCL is seeded with the spawn pose (-2.0, -0.5, yaw 0) through
`set_initial_pose` in `config/nav2_params.yaml`. In RViz, the robot appears on the map,
localized, as soon as Nav2 is active. No click needed.

**Manual** (after the robot has moved, or if localization looks wrong): in RViz click
**2D Pose Estimate**, click the robot's true position on the map and drag in its
heading direction. The laser scan (red points) should snap onto the black map walls.

Check it:
```bash
ros2 topic echo /amcl_pose --once     # position should be near the robot's real pose
```

## Run the goal script

With the launch running, in a second terminal (inside the container):

```bash
cd ~/tb3_nav_ws && source install/setup.bash
ros2 run tb3_nav_demo goal_sequence
```

It sends four goals one after another:

1. north-west, through the clutter
2. east side, **through the corridor**
3. east-south corner
4. home, back through the corridor

It prints progress every ~2 s and a summary table (result, sim-time seconds, recoveries)
at the end. Exit code 0 means all four succeeded.

`--keep-pose` reruns the sequence without resetting AMCL to the spawn pose. Use it when
the robot is not at spawn (for example, right after a previous run finished at "home").
Without the flag, the script publishes the spawn pose as the initial pose, which is right
only on a fresh launch.

A single goal by hand: in RViz click **Nav2 Goal** and drag on the map.

## Map

`maps/cluttered_room.yaml` is in the **map frame = Gazebo world frame** convention:
map (0,0) is the world origin. AMCL's initial pose and the goal coordinates rely on this.

**Shipped map:** rasterized directly from the world geometry by
`tools/generate_world_and_map.py`, a pixel-exact ground truth. The same script writes the
world file, so the two can't drift apart. To change the layout, edit the script and
re-run it:

```bash
python3 tools/generate_world_and_map.py && colcon build --symlink-install
```

**Building it with slam_toolbox**. **Untested:** this
workflow, including the origin-shift step below, has not been run on this project; the
shipped map is the generated ground truth.

```bash
# terminal 1: sim + Nav2 with slam_toolbox instead of AMCL/map_server
ros2 launch tb3_nav_demo demo.launch.py slam:=True

# terminal 2: drive around until the whole room is mapped (both halves, through the corridor)
ros2 run teleop_twist_keyboard teleop_twist_keyboard
#   (or click "Nav2 Goal" in RViz; Nav2 can plan into unknown space while mapping)

# terminal 3: save, overwriting the shipped map
cd ~/tb3_nav_ws
ros2 run nav2_map_server map_saver_cli -f src/tb3_nav_demo/maps/cluttered_room \
  --ros-args -p use_sim_time:=true
```

slam_toolbox's map frame starts **at the robot's spawn pose**, not the world origin. To keep
the map frame = world frame convention, shift the saved map's origin by the spawn
offset (yaw is 0, so a pure translation):

```bash
python3 - <<'EOF'
import pathlib, re
p = pathlib.Path('src/tb3_nav_demo/maps/cluttered_room.yaml')
s = p.read_text()
m = re.search(r'origin: \[([-\d.e]+), ([-\d.e]+), ([-\d.e]+)\]', s)
x, y, yaw = map(float, m.groups())
p.write_text(s.replace(m.group(0), f'origin: [{x - 2.0:.3f}, {y - 0.5:.3f}, {yaw}]'))
print('origin shifted by spawn offset (-2.0, -0.5)')
EOF
colcon build --symlink-install
```

Then relaunch without `slam:=True`. In RViz, the scan should line up with the map at
startup with no manual pose estimate. If it's offset by about (2.0, 0.5) m, the shift
step was skipped.

## Verify each stage

Use these when building from scratch or debugging. Every command runs inside the container.

**Sim only (before Nav2):**
```bash
ros2 launch tb3_nav_demo demo.launch.py autostart:=false
# second terminal:
ros2 topic hz /clock          # steady, high rate (sim clock)
ros2 topic hz /scan           # ~5 Hz (lidar update_rate 5)
ros2 topic hz /odom           # steady rate, nonzero
ros2 run tf2_ros tf2_echo odom base_link       # prints transforms, no errors
ros2 topic info -v /cmd_vel   # both sides geometry_msgs/msg/Twist
```

**Nav2 up:**
```bash
ros2 launch tb3_nav_demo demo.launch.py
# second terminal:
ros2 lifecycle get /bt_navigator      # active [3]
ros2 lifecycle get /amcl              # active [3]
ros2 param get /amcl use_sim_time     # Boolean value is: True
ros2 topic echo /amcl_pose --once     # near (-2.0, -0.5)
ros2 run tf2_ros tf2_echo map base_link
```

**Params differ from defaults only where commented:**
```bash
diff /opt/ros/jazzy/share/nav2_bringup/params/nav2_params.yaml \
     src/tb3_nav_demo/config/nav2_params.yaml
# expect exactly two hunks, nothing else:
#   0a1,8    the 8-line header comment
#   39a48,58 the AMCL block: NON-DEFAULT comment + set_initial_pose + initial_pose (spawn pose)
# inflation_radius stays at the defaults (0.70 / 0.7): see NOTES.md, tuning experiment
```

## Troubleshooting

**Warning `'/opt/ros/humble' in AMENT_PREFIX_PATH doesn't exist` (distrobox).**
Distrobox copies the host's environment into the container. If the host sources Humble,
its paths leak in ahead of Jazzy, including `PYTHONPATH` entries for Python 3.10. Fix: in
the Jazzy branch of `~/.bashrc`, `unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH
COLCON_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH ROS_DISTRO ROS_VERSION ROS_PYTHON_VERSION`
before `source /opt/ros/jazzy/setup.bash`, then fully exit and re-enter the container.
Details in NOTES.md #4.

**A terminal shows no topics.** It's probably a host terminal, not the container.
The container sets `ROS_DOMAIN_ID=30`; the host doesn't. Run `jazzy` first.

**Building from the host.** Distrobox shares `$HOME`, so the host can see the workspace,
but `colcon build` must run in the container. Otherwise `build/` and `install/` are built
against the wrong (or no) ROS.

**Gazebo window black or very slow.** Check rendering is hardware-accelerated:
`glxinfo -B | grep -E 'renderer|Accelerated'` (from `mesa-utils`). You should see your GPU
and `Accelerated: yes`. `llvmpipe` means software rendering: check `ls -l /dev/dri`
shows `renderD128` inside the container. As a workaround, use `headless:=True`. The lidar
still renders (it's a `gpu_lidar`), only the window goes away.

**No `/scan` (empty or missing).** The world must load the `gz-sim-sensors-system` plugin
with `<render_engine>ogre2</render_engine>`. Check with `gz topic -l | grep scan`.
If you edited the world by hand, regenerate it from `tools/generate_world_and_map.py`.

**Robot never appears in Gazebo.** A previous Gazebo may still be running.
`pkill -f "gz sim"; ros2 daemon stop`, then relaunch.

**RViz: "Frame [map] does not exist" / no map.** AMCL isn't localized yet or Nav2 isn't
active. Check `ros2 lifecycle get /amcl` and set a pose with **2D Pose Estimate**.

**Goal script stuck at "Waiting for amcl_pose".** AMCL isn't active or got no map.
Check `ros2 lifecycle get /map_server` and `/amcl`. With `--keep-pose`, the script doesn't
wait for AMCL at all.

**Edits to a new file don't take effect.** `setup.py` collects files by glob at build
time. A new file (or a regenerated world/map) needs `colcon build --symlink-install`.
For edits to existing files, check whether the install links back to `src/`:
`readlink -f install/tb3_nav_demo/share/tb3_nav_demo/config/nav2_params.yaml`. If that
doesn't end in `src/...`, rebuild after every edit.

**Robot ignores velocity commands.** Check `ros2 topic info -v /cmd_vel`. Publisher and
subscriber types must match. With these versions, the bridge expects
`geometry_msgs/msg/Twist`.

**SLAM map offset from the world** (untested workflow). The origin shift in "Map" was skipped.

## Clean-clone checklist

From a fresh clone on a machine with the Setup packages installed, inside the container:

- [ ] `git clone https://github.com/ShubhkarmanSingh7/navigation-jazzy.git ~/tb3_nav_ws && cd ~/tb3_nav_ws`
- [ ] `echo $AMENT_PREFIX_PATH` shows only `/opt/ros/jazzy` (no Humble)
- [ ] `rosdep install --from-paths src --ignore-src -y --simulate` prints nothing missing
- [ ] `colcon build --symlink-install` finishes with 0 errors and no warnings
- [ ] `source install/setup.bash && ros2 pkg prefix tb3_nav_demo` resolves
- [ ] `ls install/tb3_nav_demo/share/tb3_nav_demo/{launch,worlds,maps,config}` lists all 5 data files
- [ ] `ros2 launch tb3_nav_demo demo.launch.py`: Gazebo shows the room and robot, RViz shows the map
- [ ] `/clock`, `/scan` (~5 Hz), `/odom` publishing, `odom → base_link` TF resolves
- [ ] RViz: robot localized at startup, scan aligned with map walls
- [ ] `ros2 lifecycle get /bt_navigator` is `active`
- [ ] `ros2 run tb3_nav_demo goal_sequence` → all 4 goals `SUCCEEDED`, exit code 0
- [ ] `colcon test --packages-select tb3_nav_demo && colcon test-result --verbose` passes
- [ ] params `diff` shows only the commented NON-DEFAULT block
