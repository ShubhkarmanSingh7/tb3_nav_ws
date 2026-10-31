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

Same shape: **symptom** (exact message), **diagnosis** (commands run and what they
showed), **root cause**, **fix**, **status**.

### 8. `[gz] Exception sending a multicast message: Network is unreachable` (repeating)
- **Diagnosis:** `ip route` showed a default route via Wi-Fi, and
  `ip route get 239.255.0.7` a valid multicast route, so "no network" was ruled out.
  `ip route` also listed `docker0 ... linkdown`.
- **Likely cause:** gz-transport sends discovery multicast on every IPv4 interface; the
  Docker bridge `docker0` has an address but no link, so those sends fail.
- **Fix:** set `GZ_IP` (Wi-Fi address, or `127.0.0.1` with `lo` multicast enabled).
- **Status: unconfirmed.** The `GZ_IP` test was never run; the experiment ran with
  `GZ_IP` unset and was not affected. Treat as log noise.

### 9. `sequence size exceeds remaining buffer`; `ros2 lifecycle get /amcl` → `Node not found`
- **Diagnosis:** at the same time `/amcl_pose` was published and `map → odom` resolved, so
  AMCL was running; only the CLI's view was wrong.
- **Root cause:** stale `ros2 daemon` started before the environment fix (#4).
- **Fix:** `ros2 daemon stop`; then `/amcl` and `/bt_navigator` reported `active [3]`.
  **Status: confirmed.**

### 10. `ROS_LOCALHOST_ONLY is deprecated` warnings
- **Diagnosis:** `ROS_LOCALHOST_ONLY=0` was set but not in `~/.bashrc` or `~/.profile`.
- **Root cause:** Humble-era variable inherited from the host through distrobox.
- **Fix:** added it to the Jazzy-branch `unset` line in `~/.bashrc`. **Status: confirmed.**

### 11. `NavfnPlanner ... does not exist`; `map_server: 'yaml_filename' is not initialized`; RViz dropping every scan
- **Diagnosis:** the launch log loaded `/opt/ros/humble/lib/...`, started `gzserver`/
  `gzclient`/`spawn_entity.py` (Gazebo Classic), and printed
  `not found: "/opt/ros/jazzy/local_setup.bash"`.
- **Root cause:** the launch ran in the **host** shell (Humble), not the Jazzy container;
  the two prompts were identical. Jazzy params name plugins `pkg::Class`, Humble `pkg/Class`.
- **Fix:** run inside `jazzy`; added a `(jazzy)` prompt prefix in the container branch of
  `~/.bashrc`. No code or param change. **Status: confirmed.**

### 12. Goal 3 fails: `GridBased plugin failed to plan from (2.36, 0.47) to (2.90, -1.90)`
- **Symptom (experiment attempt 1, before the fix):** goal 3 FAILED in
  runs 1 and 5 (15 recoveries each) and needed 16 recoveries in run 4. The first plan
  succeeded (`3.30 m to go` at 2.0 s), then every replan failed; spin/wait/backup did not
  clear it.
- **Diagnosis:** `top` showed the CPU ~78 % idle (not overload); one `/clock` publisher,
  one `gz sim`, no duplicate nodes (not a double simulation). Widest-path analysis of the
  world geometry: the east box (`box_east`, x 2.2–2.8) left **0.70 m** gaps to the
  dividing wall and to the east wall, i.e. a ~0.21 m band for the robot centre after the
  0.22 m robot radius — tighter than the 0.9 m corridor (0.41 m band). Any scan mark a few
  cm into a gap is dilated by the robot radius and closes it.
- **Root cause:** world design error (mine): reachability had been checked only with
  0.24 m clearance, leaving ~9 cm of margin.
- **Fix:** `box_east` moved to x 3.1 (against the east wall) in
  `tools/generate_world_and_map.py`; world + map regenerated. Tightest point on every route
  that crosses the divider is now the corridor; goal 2 → goal 3 band 0.71 m.
  **Status: confirmed** — after the fix goal 3 succeeded 6/6 with 0 recoveries
  (experiment runs 1–6). Attempt 1 is **not** used in the results.
- **Also in attempt 1:** run 2 FAILED goal 1 after 44.0 s, stuck 0.33 m from the goal
  (outside the 0.25 m goal tolerance) with 3 `Failed to make progress`. Cause not
  diagnosed; did not recur (goal 1 succeeded 6/6 with 0 recoveries after the fix).

### 13. Script output `line 66: NNNNN Killed  setsid ros2 launch ...` (runs 2, 4, 5, 6)
- **Root cause:** `run_inflation_experiment.sh` sends SIGINT to the launch, waits 8 s,
  then SIGKILLs whatever is still shutting down (usually Gazebo).
- **Effect:** none on the data; it happens after `goal_sequence` has finished and its
  output is saved. **Status: expected.**

### 14. Open: recoveries on goal 4 (return home through the corridor)
- **Symptom (launch output of the experiment runs):** goal 4 needed recoveries in 4 of 6 runs.
  `failed to plan ... to (-2.00, -0.50)` from x 1.87–2.05, y −0.52…0.49 (east side,
  before the corridor): run 1 ×1, run 4 ×1, run 6 ×5. Run 2 instead logged 4
  `Failed to make progress` and one `Control loop missed its desired rate ... 6.2893 Hz`.
- **Status: cause not diagnosed.** It occurs with both inflation values. The pattern
  (static map passable, replans failing transiently) resembles #12, but that is
  unverified; needs a costmap snapshot at the moment of failure.

### 15. `source install/setup.bash` → `not found: "/opt/ros/humble/local_setup.bash"` (in the container)
- **Diagnosis:** `grep -n "opt/ros" install/setup.bash` → `COLCON_CURRENT_PREFIX="/opt/ros/humble"`;
  file written 2026-10-31 19:18:46, after the experiment (which built and ran in the container).
- **Root cause:** `colcon build` was run in a **host** shell. Distrobox shares `$HOME`, so
  the host build (against Humble) overwrote the workspace's `install/`; colcon records the
  underlay it was built against in `install/setup.bash`.
- **Fix:** `rm -rf build install log`, rebuild inside the container. Prevention: a
  `colcon` shell function in the Humble (host) branch of `~/.bashrc` that refuses to run
  inside `~/tb3_nav_ws`. Same family as #11 (host vs container).

### Known issue: scan visibly shifts against the map in RViz
- **Observed:** during some turns and recoveries, /scan and the local costmap appear
  offset or rotated relative to the map; obstacle marks then persist in the costmap.
- **Ruled out:** CPU/simulation lag (Gazebo real-time factor ~99 %, CPU ~78 % idle,
  2 missed control loops in 11 runs); two simulations at once (one /clock publisher,
  one gz sim); wrong wheel geometry in the robot model (0.287 vs 0.288 m separation).
- **Measured:** at rest after a run, map -> odom = (-2.067, -0.634, 1.14 deg) against the
  spawn pose (-2.0, -0.5, 0 deg), i.e. AMCL estimates odometry drift of ~0.15 m / ~1 deg.
- **Not yet done:** comparison of the estimated pose with Gazebo ground truth while
  turning, which would tell odometry/AMCL error apart from scan timing.
- **Impact:** all 24 goals in the six experiment runs still succeeded.

### Note: `[amcl] Failed to transform initial pose in time (... extrapolation into the future ...)`
Harmless. In Nav2 1.3.10 `handleInitialPose()` logs this only for a pose received after
AMCL is running, then applies the pose anyway, skipping only the motion correction for the
gap (here 9 ms). The pose came from `goal_sequence`'s `setInitialPose(spawn)`.

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
closely (keep-out drops from 0.70 m to 0.40 m, still 0.18 m beyond the robot radius),
which matters for a real robot with localization error.

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

### How it was run
`run_inflation_experiment.sh` (kept outside the repo), 2026-10-31, inside the Jazzy
container, world with `box_east` at x 3.1 (after fix #12). Each run: fresh
`demo.launch.py headless:=True` (RViz still opens), wait for `/bt_navigator` active
(~5 s every run), `ros2 run tb3_nav_demo goal_sequence`, then kill all gz/ROS processes.
Config B was generated with the sed above; a `diff` against config A confirmed exactly two
lines changed, both `inflation_radius: 0.40`. Environment recorded at run time:
(Nav2 1.3.10, nav2_minimal_tb3_sim 1.0.1, gz sim 8.10.0, `GZ_IP` unset).

### Results

Copied from the `goal_sequence` summary printed at the end of each run (A1–A3 = runs 1–3,
B1–B3 = runs 4–6). The raw outputs were saved locally under `logs/` and are not included
in this repository.
Time = sim seconds per goal from the script's summary; R = recoveries
(`number_of_recoveries` from the NavigateToPose feedback).

| Run | Config | G1 time / R | G2 (corridor) time / R | G3 time / R | G4 (corridor) time / R | All succeeded? |
|---|---|---|---|---|---|---|
| A1 | 0.70 | 13.7 / 0 | 14.1 / 0 | 15.3 / 0 | 30.3 / 1 | yes |
| A2 | 0.70 | 13.6 / 0 | 13.8 / 0 | 15.7 / 0 | 74.4 / 5 | yes |
| A3 | 0.70 | 12.6 / 0 | 14.3 / 0 | 16.1 / 0 | 31.9 / 0 | yes |
| B1 | 0.40 | 10.4 / 0 | 13.8 / 0 | 13.6 / 0 | 27.3 / 1 | yes |
| B2 | 0.40 | 10.9 / 0 | 13.5 / 0 | 13.9 / 0 | 25.3 / 0 | yes |
| B3 | 0.40 | 10.6 / 0 | 12.6 / 0 | 14.1 / 0 | 32.5 / 6 | yes |

Per run, total time / total recoveries: A 73.4 / 1, 117.5 / 5, 74.9 / 0;
B 65.1 / 1, 63.6 / 0, 69.8 / 6. Totals over 3 runs: **A 6 recoveries, B 7**.

**Observed behavior, A (0.70)** — from the run output only:
all 12 goals succeeded. Goals 1–3 had 0 recoveries in every run (G1 12.6–13.7 s,
G2 13.8–14.3 s, G3 15.3–16.1 s). Goal 4 took 30.3–74.4 s with 0–5 recoveries; the 74.4 s
run (A2) logged 4 `Failed to make progress` (see #14).

**Observed behavior, B (0.40)** — from the run output only:
all 12 goals succeeded. Goals 1–3 had 0 recoveries in every run (G1 10.4–10.9 s,
G2 12.6–13.8 s, G3 13.6–14.1 s). Goal 4 took 25.3–32.5 s with 0–6 recoveries; the
6-recovery run (B3) logged 5 planner failures from the east side (see #14).

Compared with A, B was faster on goal 1 in every run (each B time below every A time) and on
goal 3 in every run; goal 2 (through the corridor) overlapped (A 13.8–14.3 s, B 12.6–13.8 s).
Path centring, weaving and closest pass to obstacles were **not** measured; they need the
visual check in RViz described above.

### Decision
Rule (set before the runs): keep the value that completes all goals reliably with fewer
recoveries; switch to 0.40 only if B wins.

- Reliability: tie — both configs completed 12/12 goals.
- Recoveries: B did **not** have fewer (7 vs 6). Both totals come from goal 4 only and are
  dominated by one run each (A2: 5, B3: 6), so with 3 runs the difference is noise either
  way. Neither config had recoveries in the clutter (goal 1).

**Result: B does not win under the rule, so `inflation_radius` stays at the default 0.70 in
both costmaps; `config/nav2_params.yaml` is unchanged.** B's consistently shorter times on
goals 1 and 3 are recorded above but are not the criterion, and the rule was not changed
after seeing the data. A follow-up with more runs (or a time-based criterion decided in
advance) would be needed to justify 0.40, together with the clearance trade-off
(keep-out 0.40 m instead of 0.70 m, 0.18 m beyond the robot radius).
