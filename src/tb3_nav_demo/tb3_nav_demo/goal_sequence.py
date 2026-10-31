"""
Send 4 sequential Nav2 goals around the obstacles and report each result.

Route: clutter (west) -> through the 0.9 m corridor -> east corner -> back home.
Coordinates are in the map frame, which equals the Gazebo world frame.

  ros2 run tb3_nav_demo goal_sequence               # fresh launch, robot at spawn
  ros2 run tb3_nav_demo goal_sequence --keep-pose   # rerun without re-localizing
"""

import argparse
import math
import sys

from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
import rclpy
from rclpy.duration import Duration
from rclpy.parameter import Parameter
from rclpy.utilities import remove_ros_args

# Spawn pose: default of nav2_minimal_tb3_sim/launch/spawn_tb3.launch.py,
# also set as AMCL's initial_pose in config/nav2_params.yaml.
SPAWN = (-2.0, -0.5, 0.0)

# (label, x, y, yaw) -- every goal has >= 0.6 m clearance to the nearest obstacle
GOALS = [
    ('1 clutter, north-west', -1.7, 1.9, 0.0),
    ('2 east side, through corridor', 2.6, 0.5, 0.0),
    ('3 east-south corner', 2.9, -1.9, math.pi),
    ('4 home, back through corridor', SPAWN[0], SPAWN[1], SPAWN[2]),
]

GOAL_TIMEOUT = Duration(seconds=180.0)   # sim time; cancel a goal that runs longer


def make_pose(nav, x, y, yaw):
    pose = PoseStamped()
    pose.header.frame_id = 'map'
    pose.header.stamp = nav.get_clock().now().to_msg()
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.orientation.z = math.sin(yaw / 2.0)
    pose.pose.orientation.w = math.cos(yaw / 2.0)
    return pose


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        '--keep-pose', action='store_true',
        help='do not publish the spawn pose to AMCL (use when the robot has moved)')
    args = parser.parse_args(remove_ros_args(sys.argv)[1:])

    rclpy.init()
    nav = BasicNavigator()
    # Goal stamps and timeouts must use Gazebo's clock, like the rest of the stack.
    nav.set_parameters([Parameter('use_sim_time', Parameter.Type.BOOL, True)])

    if args.keep_pose:
        # waitUntilNav2Active(localizer='amcl') always publishes the navigator's stored
        # initial pose first, which would reset AMCL. 'robot_localization' is the
        # commander's documented non-AMCL path: it skips the initial-pose step and
        # only waits for bt_navigator to be active.
        nav.waitUntilNav2Active(localizer='robot_localization')
    else:
        # BasicNavigator's stored initial pose defaults to (0, 0). Without this line,
        # waitUntilNav2Active() would publish (0, 0) and throw AMCL off the robot.
        nav.setInitialPose(make_pose(nav, *SPAWN))
        nav.waitUntilNav2Active()

    summary = []
    for label, x, y, yaw in GOALS:
        nav.info(f'Goal {label}: ({x:.2f}, {y:.2f}, yaw {math.degrees(yaw):.0f} deg)')
        if not nav.goToPose(make_pose(nav, x, y, yaw)):
            summary.append((label, 'REJECTED', 0.0, 0))
            break

        elapsed, recoveries, i, cancelled = 0.0, 0, 0, False
        while not nav.isTaskComplete():
            fb = nav.getFeedback()
            if fb:
                elapsed = Duration.from_msg(fb.navigation_time).nanoseconds / 1e9
                recoveries = fb.number_of_recoveries
                i += 1
                if i % 20 == 0:   # isTaskComplete spins ~0.1 s, so about every 2 s
                    nav.info(f'  {fb.distance_remaining:.2f} m to go, '
                             f'{elapsed:.1f} s, recoveries {recoveries}')
                if not cancelled and Duration.from_msg(fb.navigation_time) > GOAL_TIMEOUT:
                    nav.warn('  timeout, cancelling goal')
                    nav.cancelTask()
                    cancelled = True

        result = nav.getResult()
        summary.append((label, result.name, elapsed, recoveries))
        if result != TaskResult.SUCCEEDED:
            nav.error(f'  {result.name}, stopping the sequence')
            break
        nav.info(f'  reached in {elapsed:.1f} s (sim), recoveries {recoveries}')

    print('\n goal                            result      time(s)  recoveries')
    for label, result, elapsed, recoveries in summary:
        print(f' {label:31s} {result:10s} {elapsed:7.1f}  {recoveries:5d}')

    ok = len(summary) == len(GOALS) and all(r == 'SUCCEEDED' for _, r, _, _ in summary)
    nav.destroy_node()
    rclpy.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
