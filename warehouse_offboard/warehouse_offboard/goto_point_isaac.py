#!/usr/bin/env python3

import math
from typing import Dict, List, Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from px4_msgs.msg import OffboardControlMode
from px4_msgs.msg import TrajectorySetpoint
from px4_msgs.msg import VehicleCommand
from px4_msgs.msg import VehicleLocalPosition
from px4_msgs.msg import VehicleLandDetected
from std_msgs.msg import String


def normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


class GotoPointIsaac(Node):
    def __init__(self):
        super().__init__('goto_point_isaac')

        px4_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        self.offboard_control_mode_publisher = self.create_publisher(
            OffboardControlMode,
            '/fmu/in/offboard_control_mode',
            px4_qos
        )
        self.trajectory_setpoint_publisher = self.create_publisher(
            TrajectorySetpoint,
            '/fmu/in/trajectory_setpoint',
            px4_qos
        )
        self.vehicle_command_publisher = self.create_publisher(
            VehicleCommand,
            '/fmu/in/vehicle_command',
            px4_qos
        )

        self.vehicle_local_position_subscriber = self.create_subscription(
            VehicleLocalPosition,
            '/fmu/out/vehicle_local_position_v1',
            self.vehicle_local_position_callback,
            px4_qos
        )
        self.vehicle_land_detected_subscriber = self.create_subscription(
            VehicleLandDetected,
            '/fmu/out/vehicle_land_detected',
            self.vehicle_land_detected_callback,
            px4_qos
        )

        self.mission_target_subscriber = self.create_subscription(
            String,
            '/mission_target_name',
            self.mission_target_callback,
            10
        )
        self.mission_status_publisher = self.create_publisher(
            String,
            '/mission_status_text',
            10
        )

        self.declare_parameter('reach_tolerance', 0.30)
        self.declare_parameter('hover_time_sec', 3.0)
        self.declare_parameter('preland_hover_time_sec', 2.0)
        self.declare_parameter('preland_xy_tolerance', 0.10)
        self.declare_parameter('yaw_align_deg', 90.0)

        self.declare_parameter('waypoint_names', ['A-1', 'A-2', 'B-1', 'B-2'])
        self.declare_parameter('waypoint_local_dx', [-1.2, 1.2, -1.2, 1.2])
        self.declare_parameter('waypoint_local_dy', [2.9, 2.9, 0.5, 0.5])
        self.declare_parameter('waypoint_local_z', [-1.6, -1.6, -1.6, -1.6])

        self.reach_tolerance = float(self.get_parameter('reach_tolerance').value)
        self.hover_time_sec = float(self.get_parameter('hover_time_sec').value)
        self.preland_hover_time_sec = float(self.get_parameter('preland_hover_time_sec').value)
        self.preland_xy_tolerance = float(self.get_parameter('preland_xy_tolerance').value)
        self.yaw_align_deg = float(self.get_parameter('yaw_align_deg').value)

        waypoint_names = list(self.get_parameter('waypoint_names').value)
        waypoint_local_dx = list(self.get_parameter('waypoint_local_dx').value)
        waypoint_local_dy = list(self.get_parameter('waypoint_local_dy').value)
        waypoint_local_z = list(self.get_parameter('waypoint_local_z').value)

        n = len(waypoint_names)
        if not (
            len(waypoint_local_dx) == n and
            len(waypoint_local_dy) == n and
            len(waypoint_local_z) == n
        ):
            raise ValueError(
                'waypoint_names, waypoint_local_dx, waypoint_local_dy, waypoint_local_z length mismatch'
            )

        self.waypoint_map: Dict[str, List[float]] = {}
        for i in range(n):
            self.waypoint_map[str(waypoint_names[i]).upper()] = [
                float(waypoint_local_dx[i]),
                float(waypoint_local_dy[i]),
                float(waypoint_local_z[i]),
            ]

        self.current_x = 0.0
        self.current_y = 0.0
        self.current_z = 0.0
        self.current_heading = 0.0

        self.position_valid = False
        self.received_position_once = False
        self.landed = False

        self.home_initialized = False
        self.home_x: Optional[float] = None
        self.home_y: Optional[float] = None
        self.home_z: Optional[float] = None
        self.home_yaw: Optional[float] = None

        self.target_name: Optional[str] = None
        self.target_local_x: Optional[float] = None
        self.target_local_y: Optional[float] = None
        self.target_local_z: Optional[float] = None

        self.pending_target_name: Optional[str] = None
        self.last_finished_target: Optional[str] = None

        self.phase = 'WAIT_HOME'
        self.prev_phase = ''

        self.offboard_setpoint_counter = 0
        self.hover_counter = 0
        self.hover_limit = max(1, int(self.hover_time_sec / 0.1))

        self.preland_hover_counter = 0
        self.preland_hover_limit = max(1, int(self.preland_hover_time_sec / 0.1))

        self.land_command_sent = False
        self.disarm_sent = False

        self.timer = self.create_timer(0.1, self.timer_callback)

        self.get_logger().info('goto_point_isaac node started')
        self.get_logger().info('Waiting for valid local position before first mission...')
        self.publish_mission_status('WAITING_FOR_COMMAND')

    def publish_mission_status(self, text: str):
        msg = String()
        msg.data = text
        self.mission_status_publisher.publish(msg)

    def mission_target_callback(self, msg: String):
        target_name = msg.data.strip().upper()

        if target_name not in self.waypoint_map:
            self.get_logger().warn(f'Unknown mission target received: {target_name}')
            self.publish_mission_status('MISSION_REJECTED:UNKNOWN_TARGET')
            return

        if self.phase not in ['WAIT_HOME', 'FINISHED']:
            self.get_logger().warn(
                f'Received {target_name}, but mission is already running (phase={self.phase})'
            )
            self.publish_mission_status('MISSION_REJECTED:BUSY')
            return

        self.pending_target_name = target_name
        self.get_logger().info(f'Pending mission target set: {target_name}')
        self.publish_mission_status(f'COMMAND_RECEIVED:{target_name}')

    def vehicle_local_position_callback(self, msg: VehicleLocalPosition):
        if not self.received_position_once:
            self.get_logger().info(
                f'Local position received | xy_valid={msg.xy_valid}, '
                f'z_valid={msg.z_valid}, x={msg.x:.2f}, y={msg.y:.2f}, '
                f'z={msg.z:.2f}, heading={msg.heading:.2f}'
            )
            self.received_position_once = True

        self.current_x = float(msg.x)
        self.current_y = float(msg.y)
        self.current_z = float(msg.z)
        self.current_heading = float(msg.heading)
        self.position_valid = bool(msg.xy_valid and msg.z_valid)

    def vehicle_land_detected_callback(self, msg: VehicleLandDetected):
        self.landed = bool(msg.landed)

    def start_new_mission(self, selected_target_name: str):
        if not self.position_valid:
            self.get_logger().warn('Cannot start new mission: local position is invalid')
            self.publish_mission_status('MISSION_REJECTED:POSITION_INVALID')
            return

        self.home_x = self.current_x
        self.home_y = self.current_y
        self.home_z = self.current_z
        self.home_yaw = self.current_heading
        self.home_initialized = True

        self.target_name = selected_target_name

        dx, dy, z = self.waypoint_map[self.target_name]
        self.target_local_x = self.home_x + dx
        self.target_local_y = self.home_y + dy
        self.target_local_z = z

        self.phase = 'TAKEOFF'
        self.prev_phase = ''
        self.offboard_setpoint_counter = 0
        self.hover_counter = 0
        self.preland_hover_counter = 0
        self.land_command_sent = False
        self.disarm_sent = False

        self.get_logger().info(
            f'New mission selected: {self.target_name} | '
            f'local target=({self.target_local_x:.2f}, {self.target_local_y:.2f}, {self.target_local_z:.2f})'
        )
        self.get_logger().info(
            f'Home=({self.home_x:.2f}, {self.home_y:.2f}, {self.home_z:.2f}), yaw={self.home_yaw:.2f}'
        )

        self.publish_mission_status(f'MISSION_STARTED:{self.target_name}')

    def aligned_yaw(self) -> float:
        if self.home_yaw is None:
            return 0.0
        return normalize_angle(self.home_yaw + math.radians(self.yaw_align_deg))

    def reached_x(self, target_x: float, tolerance: Optional[float] = None) -> bool:
        tol = self.reach_tolerance if tolerance is None else tolerance
        return abs(self.current_x - target_x) < tol

    def reached_y(self, target_y: float, tolerance: Optional[float] = None) -> bool:
        tol = self.reach_tolerance if tolerance is None else tolerance
        return abs(self.current_y - target_y) < tol

    def reached_z(self, target_z: float, tolerance: Optional[float] = None) -> bool:
        tol = self.reach_tolerance if tolerance is None else tolerance
        return abs(self.current_z - target_z) < tol

    def reached_yaw(self, target_yaw: float, tolerance: float = 0.08) -> bool:
        return abs(normalize_angle(self.current_heading - target_yaw)) < tolerance

    def reached_home_xy_precise(self) -> bool:
        if self.home_x is None or self.home_y is None:
            return False
        return (
            abs(self.current_x - self.home_x) < self.preland_xy_tolerance and
            abs(self.current_y - self.home_y) < self.preland_xy_tolerance
        )

    def reached_home_yaw(self) -> bool:
        if self.home_yaw is None:
            return False
        return self.reached_yaw(self.home_yaw, tolerance=0.08)

    def compute_distance(self, x1, y1, z1, x2, y2, z2):
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)

    def publish_offboard_control_mode(self):
        msg = OffboardControlMode()
        msg.timestamp = self.get_clock().now().nanoseconds // 1000
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        msg.thrust_and_torque = False
        msg.direct_actuator = False
        self.offboard_control_mode_publisher.publish(msg)

    def publish_trajectory_setpoint(self, x, y, z, yaw):
        msg = TrajectorySetpoint()
        msg.timestamp = self.get_clock().now().nanoseconds // 1000
        msg.position = [float(x), float(y), float(z)]
        msg.yaw = float(yaw)
        self.trajectory_setpoint_publisher.publish(msg)

    def publish_vehicle_command(self, command, param1=0.0, param2=0.0):
        msg = VehicleCommand()
        msg.timestamp = self.get_clock().now().nanoseconds // 1000
        msg.param1 = float(param1)
        msg.param2 = float(param2)
        msg.command = int(command)
        msg.target_system = 1
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self.vehicle_command_publisher.publish(msg)

    def get_phase_target(self):
        if (
            self.home_x is None or self.home_y is None or self.home_z is None or
            self.home_yaw is None or
            self.target_local_x is None or self.target_local_y is None or self.target_local_z is None
        ):
            return None

        if self.phase == 'TAKEOFF':
            return [self.home_x, self.home_y, self.target_local_z, self.home_yaw]

        if self.phase == 'YAW_ALIGN':
            return [self.home_x, self.home_y, self.target_local_z, self.aligned_yaw()]

        if self.phase == 'MOVE_GLOBAL_Y':
            return [self.home_x, self.target_local_y, self.target_local_z, self.aligned_yaw()]

        if self.phase == 'MOVE_GLOBAL_X':
            return [self.target_local_x, self.target_local_y, self.target_local_z, self.aligned_yaw()]

        if self.phase == 'HOVER':
            return [self.target_local_x, self.target_local_y, self.target_local_z, self.aligned_yaw()]

        if self.phase == 'RETURN_GLOBAL_X':
            return [self.home_x, self.target_local_y, self.target_local_z, self.aligned_yaw()]

        if self.phase == 'RETURN_GLOBAL_Y':
            return [self.home_x, self.home_y, self.target_local_z, self.aligned_yaw()]

        if self.phase == 'PRELAND_YAW_HOME':
            return [self.home_x, self.home_y, self.target_local_z, self.home_yaw]

        if self.phase == 'PRELAND_SETTLE':
            return [self.home_x, self.home_y, self.target_local_z, self.home_yaw]

        return None

    def timer_callback(self):
        if self.phase == 'WAIT_HOME':
            if not self.position_valid:
                return

            if self.pending_target_name is not None:
                selected = self.pending_target_name
                self.pending_target_name = None
                self.start_new_mission(selected)
            return

        if self.phase == 'FINISHED':
            if self.pending_target_name is not None:
                selected = self.pending_target_name
                self.pending_target_name = None
                self.start_new_mission(selected)
            return

        if self.phase not in ['WAIT_DISARM']:
            self.publish_offboard_control_mode()

            target_pose = self.get_phase_target()
            if target_pose is not None:
                self.publish_trajectory_setpoint(
                    target_pose[0], target_pose[1], target_pose[2], target_pose[3]
                )

            if self.offboard_setpoint_counter == 10:
                self.get_logger().info('Switching to OFFBOARD mode')
                self.publish_vehicle_command(
                    VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                    param1=1.0,
                    param2=6.0
                )
                self.get_logger().info('Arming vehicle')
                self.publish_vehicle_command(
                    VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,
                    param1=1.0
                )

            if self.offboard_setpoint_counter < 11:
                self.offboard_setpoint_counter += 1
                return

        if self.phase != self.prev_phase:
            self.get_logger().info(f'Phase changed -> {self.phase}')
            self.prev_phase = self.phase

        if self.phase == 'TAKEOFF':
            if self.reached_z(self.target_local_z):
                self.phase = 'YAW_ALIGN'

        elif self.phase == 'YAW_ALIGN':
            if self.reached_yaw(self.aligned_yaw(), tolerance=0.12):
                self.phase = 'MOVE_GLOBAL_Y'

        elif self.phase == 'MOVE_GLOBAL_Y':
            if self.reached_y(self.target_local_y):
                self.phase = 'MOVE_GLOBAL_X'

        elif self.phase == 'MOVE_GLOBAL_X':
            if self.reached_x(self.target_local_x):
                self.phase = 'HOVER'

        elif self.phase == 'HOVER':
            self.hover_counter += 1
            if self.hover_counter >= self.hover_limit:
                self.hover_counter = 0
                self.phase = 'RETURN_GLOBAL_X'

        elif self.phase == 'RETURN_GLOBAL_X':
            if self.reached_x(self.home_x):
                self.phase = 'RETURN_GLOBAL_Y'

        elif self.phase == 'RETURN_GLOBAL_Y':
            if self.reached_y(self.home_y):
                self.phase = 'PRELAND_YAW_HOME'

        elif self.phase == 'PRELAND_YAW_HOME':
            if self.reached_home_yaw():
                self.phase = 'PRELAND_SETTLE'

        elif self.phase == 'PRELAND_SETTLE':
            if self.reached_home_xy_precise():
                self.preland_hover_counter += 1
                if self.preland_hover_counter >= self.preland_hover_limit:
                    self.preland_hover_counter = 0
                    self.phase = 'LAND_CMD'
            else:
                self.preland_hover_counter = 0

        elif self.phase == 'LAND_CMD':
            if not self.land_command_sent:
                self.get_logger().info('Sending NAV_LAND command')
                self.publish_vehicle_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
                self.land_command_sent = True
                self.phase = 'WAIT_DISARM'

        elif self.phase == 'WAIT_DISARM':
            if self.landed and not self.disarm_sent:
                self.get_logger().info('Touchdown detected, disarming')
                self.publish_vehicle_command(
                    VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,
                    param1=0.0
                )
                self.disarm_sent = True
                self.phase = 'FINISHED'
                self.last_finished_target = self.target_name
                self.publish_mission_status(f'MISSION_FINISHED:{self.last_finished_target}')
                self.get_logger().info('Mission finished')


def main(args=None):
    rclpy.init(args=args)
    node = GotoPointIsaac()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('goto_point_isaac node stopped by user')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
