# Build notes

Every error and pitfall hit while building this repo, with root cause and fix, followed by
the parameter-tuning experiment. Newest entries at the bottom of each section.

## Error log

### 1. Package versions from the ROS index didn't match the machine
- **Symptom:** the ROS index listed `nav2_minimal_tb3_sim` 1.3.0 for Jazzy; `apt-cache policy`
  on the machine reported `1.0.1-1noble...`.
- **Root cause:** the index shows the latest upstream release, not what the Ubuntu apt
  snapshot on this machine carries.
- **Fix:** README "Versions" lists only what `apt-cache policy` printed locally.

### 2. `glxinfo: command not found`
- **Symptom:** the GPU check failed before it ran.
- **Root cause:** the distrobox image is minimal; `mesa-utils` isn't installed.
- **Fix:** `sudo apt install -y mesa-utils`. Result: `AMD Radeon Graphics (radeonsi, renoir)`,
  `Accelerated: yes`, so hardware rendering works through `/dev/dri`. No dedicated GPU is
  needed; the Ryzen's integrated Radeon is enough.

### 3. `gedit: command not found` in the container
- **Root cause:** no GUI editors in the container image.
- **Fix:** distrobox shares `$HOME`, so files can be edited with the host's editor; or write
  files with a quoted heredoc (`cat > file << 'EOF'`). Only building and running must
  happen inside the container.

### 4. `WARNING: The path '/opt/ros/humble' in AMENT_PREFIX_PATH doesn't exist`
- **Symptom:** shown on every `colcon build`.
- **Diagnosis:**
  - `echo $AMENT_PREFIX_PATH` → `.../install/tb3_nav_demo : /opt/ros/jazzy : /opt/ros/humble`
  - `~/.bashrc` sources Jazzy *or* Humble (`if`/`elif`), so the container never sources Humble.
  - Sourcing *prepends*, so Humble being **after** Jazzy means it was already in the
    variable before Jazzy was sourced.
  - `ls /run/host/opt/ros` → `humble`: the host has Humble.
  - `PYTHONPATH` also had `/opt/ros/humble/lib/python3.10/site-packages`.
- **Root cause:** distrobox passes the host environment into the container. The host
  (Ubuntu 22.04) sources Humble via the shared `~/.bashrc`, so Humble paths leaked into
  the Jazzy (24.04, Python 3.12) container. Harmless only because `/opt/ros/humble` doesn't
  exist inside the container; otherwise Jazzy could import Python 3.10 Humble packages.
  An earlier `unset ROS_DISTRO` line in `.bashrc` had silenced the related ROS_DISTRO
  warning but left the paths behind.
- **Fix:** in the Jazzy branch of `~/.bashrc`, before `source /opt/ros/jazzy/setup.bash`:
  ```bash
  unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH \
        ROS_DISTRO ROS_VERSION ROS_PYTHON_VERSION
  ```
  then fully exit and re-enter the container (re-sourcing in the same shell keeps the old
  values). The host still takes the Humble branch, unaffected. Backup kept at
  `~/.bashrc.bak-before-ros-fix`.

### 5. `nav2_simple_commander` would have reset AMCL to the origin (caught in code review)
- **Symptom (would-be):** robot localized at the wrong place right as the goal script starts.
- **Root cause:** in nav2_simple_commander 1.3.10, `waitUntilNav2Active(localizer='amcl')`
  calls `_waitForInitialPose()`, which **publishes the navigator's stored initial pose before
  checking** for `/amcl_pose`. That stored pose defaults to (0, 0), while the robot spawns
  at (-2.0, -0.5).
- **Fix:** `goal_sequence.py` calls `setInitialPose(spawn)` before
  `waitUntilNav2Active()`. For reruns from a non-spawn position, `--keep-pose` uses
  `localizer='robot_localization'`, which skips the initial-pose publish.

### 6. Assumption corrected: `cmd_vel` is `Twist`, not `TwistStamped`
- **Assumption:** Jazzy Nav2 might publish `TwistStamped`, mismatching the bridge.
- **Evidence:** `nav2_minimal_tb3_sim/configs/turtlebot3_waffle_bridge.yaml` bridges
  `geometry_msgs/msg/Twist`; the stock `nav2_params.yaml` has no `stamped` parameter.
- **Fix:** none needed; nothing changed. Confirm at runtime with `ros2 topic info -v /cmd_vel`.

### 7. `setup.py` would have failed `colcon test` (flake8)
- **Symptom:** `I100 Import statements are in the wrong order` and
  `E501 line too long (103 > 99 characters)`.
- **Root cause:** `ament_flake8` uses Google import order (`from glob import glob` before
  `import os`) and a 99-character limit; the hand-edited `setup.py` broke both.
- **Fix:** reordered imports, wrapped the description string. Launch file and goal script
  were already clean under flake8 + pep257.

### Stages 3–7 (runtime)

Log each new error here in the same shape: **symptom** (exact message), **diagnosis**
(commands run and what they showed), **root cause**, **fix**.

| # | Stage | Symptom | Root cause | Fix |
|---|---|---|---|---|
| 8 | | | | |

---

## Parameter-tuning experiment: inflation radius vs the 0.9 m corridor

### Why this parameter
The corridor is 0.9 m wide, so its centreline is 0.45 m from each wall. Jazzy's default
`inflation_radius` is **0.70 m** (both costmaps), with `cost_scaling_factor` 3.0 and
`robot_radius` 0.22. Inflation cost at distance *d* from an obstacle is
`252 · exp(−3.0 · (d − 0.22))` for 0.22 < d ≤ inflation_radius. So:

| Spot | Clearance | Cost @ 0.70 (default) | Cost @ 0.40 |
|---|---|---|---|
| Corridor centreline | 0.45 m | **126** | 0 (a 0.10 m wide zero-cost strip) |
| Goals 1 and 3 | 0.60 m | ~80 | 0 |
| Spawn, goal 2 | >= 0.80 m | 0 | 0 |

With the default, the **entire corridor** is high-cost: no cell in it is below 126. The
planner still routes through (it's the only way east), but MPPI's cost critic penalizes
every sampled trajectory inside it.

**Hypothesis:** with the default, the robot slows and weaves in the corridor. At
`inflation_radius: 0.40`, the corridor centre becomes free, and the robot passes
straighter and faster. The trade-off is that paths in the clutter hug obstacles more
closely (keep-out drops from 0.70 m to 0.40 m, still 0.18 m beyond the robot radius), which matters for a real robot with
localization error.

### Procedure
Run each config **3 times** (MPPI is sampling-based, so single runs are noisy) from a fresh
launch each time:

```bash
# A: baseline (defaults)
ros2 launch tb3_nav_demo demo.launch.py
ros2 run tb3_nav_demo goal_sequence          # second terminal; copy the summary table

# B: inflation_radius 0.40 in BOTH costmaps (local file is 0.70, global is 0.7)
sed -E 's/inflation_radius: 0\.70?$/inflation_radius: 0.40/' \
  src/tb3_nav_demo/config/nav2_params.yaml > /tmp/params_infl040.yaml
grep -n inflation_radius /tmp/params_infl040.yaml      # expect two lines, both 0.40
ros2 launch tb3_nav_demo demo.launch.py params_file:=/tmp/params_infl040.yaml
ros2 run tb3_nav_demo goal_sequence
```

During each run, watch RViz with the **global costmap** visible. Note whether the global path
is centred in the corridor, whether the local trajectory oscillates, and how close the robot
passes the cylinders and boxes. A screenshot of the costmap in the corridor for A and B
makes the difference obvious.

### Results (fill in from the goal_sequence summaries)

Time = sim seconds per goal from the script's summary; R = recoveries.

| Run | Config | G1 time / R | G2 (corridor) time / R | G3 time / R | G4 (corridor) time / R | All succeeded? |
|---|---|---|---|---|---|---|
| A1 | 0.70 | | | | | |
| A2 | 0.70 | | | | | |
| A3 | 0.70 | | | | | |
| B1 | 0.40 | | | | | |
| B2 | 0.40 | | | | | |
| B3 | 0.40 | | | | | |

**Observed behavior, A (before):**
_(corridor speed, weaving, path centring, closest pass to an obstacle)_

**Observed behavior, B (after):**
_(same points)_

### Decision
_(fill in after the runs)_ Keep the value that completes all goals reliably with fewer
recoveries. If B wins, set `inflation_radius: 0.40` in **both** costmaps in
`config/nav2_params.yaml`, marked `# NON-DEFAULT` with the measured reason, and note
the obstacle-clearance trade-off. If B shows near-collisions or extra recoveries in the
clutter, keep the default and record why.
