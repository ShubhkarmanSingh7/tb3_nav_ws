"""
One launch file: Gazebo Harmonic + TurtleBot3 Waffle + Nav2 + RViz, all on sim time.

A thin wrapper around nav2_bringup's tb3_simulation_launch.py (Jazzy). It passes in
this package's world, map and params and changes nothing else, so the robot model,
ros_gz bridge and spawn come straight from nav2_minimal_tb3_sim.

  ros2 launch tb3_nav_demo demo.launch.py              # navigate on the saved map
  ros2 launch tb3_nav_demo demo.launch.py slam:=True   # build a map with slam_toolbox
  ros2 launch tb3_nav_demo demo.launch.py headless:=True   # no Gazebo window
  ros2 launch tb3_nav_demo demo.launch.py autostart:=false # sim only, Nav2 inactive
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    pkg = get_package_share_directory('tb3_nav_demo')
    nav2_bringup = get_package_share_directory('nav2_bringup')

    args = [
        DeclareLaunchArgument(
            'world', default_value=os.path.join(pkg, 'worlds', 'cluttered_room.sdf.xacro'),
            description='World file (run through xacro by the stock launch)'),
        DeclareLaunchArgument(
            'map', default_value=os.path.join(pkg, 'maps', 'cluttered_room.yaml'),
            description='Map yaml for map_server/AMCL (ignored when slam:=True)'),
        DeclareLaunchArgument(
            'params_file', default_value=os.path.join(pkg, 'config', 'nav2_params.yaml'),
            description='Nav2 parameters'),
        DeclareLaunchArgument(
            'slam', default_value='False',
            description='True: slam_toolbox builds a map instead of AMCL + saved map'),
        # The stock launch defaults headless to True (no Gazebo window). A demo wants it.
        DeclareLaunchArgument(
            'headless', default_value='False',
            description='True: Gazebo server only, no GUI window (RViz still opens)'),
        # False = Nav2 nodes load but stay inactive, so the sim topics can be checked
        # on their own before navigation starts (README "Verify each stage").
        DeclareLaunchArgument(
            'autostart', default_value='true',
            description='false: bring up sim + RViz, leave Nav2 inactive'),
    ]

    sim_and_nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup, 'launch', 'tb3_simulation_launch.py')),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'map': LaunchConfiguration('map'),
            'params_file': LaunchConfiguration('params_file'),
            'slam': LaunchConfiguration('slam'),
            'headless': LaunchConfiguration('headless'),
            'autostart': LaunchConfiguration('autostart'),
            'use_sim_time': 'true',
            'use_rviz': 'True',
        }.items(),
    )

    return LaunchDescription(args + [sim_and_nav2])
