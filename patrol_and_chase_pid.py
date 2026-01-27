#! /usr/bin/env python3

import rospy
import math
import numpy as np
from geometry_msgs.msg import PoseStamped, Twist, Point
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest
from tf.transformations import euler_from_quaternion

# ==========================================
# [수정된 설정값] 안전거리 확보
# ==========================================
HOVER_HEIGHT = 2.5

# 기존: [18000, 22000] -> 너무 가까움
# 수정: [2000, 5000] -> 화면에 작게 보여도 멈춤 (멀리서 추적)
TARGET_AREA_RANGE = [2000, 5000] 

# 회전 민감도 (P, I, D)
PID_YAW = [1.2, 0.0, 0.0] 

# 추적 속도 (너무 빠르면 지나침 -> 0.3으로 감속)
CHASE_SPEED = 0.3 
PATROL_SPEED = 0.5
PATROL_TURN_RATE = 0.3
LOST_TIMEOUT = 2.0
# ==========================================

class PatrolChaseNode:
    def __init__(self):
        rospy.init_node("patrol_chase_pid_node")
        self.current_state = State()
        self.current_pose = PoseStamped()
        self.target_info = Point()
        self.last_detection_time = 0
        self.is_chasing = False
        self.pError_yaw = 0

        # UAV0 기준 토픽
        rospy.Subscriber("mavros/state", State, self.state_cb)
        rospy.Subscriber("mavros/local_position/pose", PoseStamped, self.pose_cb)
        rospy.Subscriber("/tracker/target_pos", Point, self.tracker_cb)
        self.vel_pub = rospy.Publisher("mavros/setpoint_velocity/cmd_vel_unstamped", Twist, queue_size=10)

        rospy.wait_for_service("mavros/cmd/arming")
        self.arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
        rospy.wait_for_service("mavros/set_mode")
        self.set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

    def state_cb(self, msg): self.current_state = msg
    def pose_cb(self, msg): self.current_pose = msg
    def tracker_cb(self, msg):
        self.target_info = msg
        # 면적(z)이 0보다 크면 감지된 것으로 판단
        if self.target_info.z > 0: 
            self.last_detection_time = rospy.Time.now().to_sec()

    def get_current_yaw(self):
        q = self.current_pose.pose.orientation
        (_, _, yaw) = euler_from_quaternion([q.x, q.y, q.z, q.w])
        return yaw

    def run(self):
        rate = rospy.Rate(20)
        while not rospy.is_shutdown() and not self.current_state.connected: rate.sleep()
        
        # 연결 유지용 더미 데이터
        for _ in range(100): self.vel_pub.publish(Twist()); rate.sleep()

        offb_set_mode = SetModeRequest(); offb_set_mode.custom_mode = 'OFFBOARD'
        arm_cmd = CommandBoolRequest(); arm_cmd.value = True
        last_req = rospy.Time.now()

        while not rospy.is_shutdown():
            if self.current_state.mode != "OFFBOARD" and (rospy.Time.now() - last_req) > rospy.Duration(5.0):
                self.set_mode_client.call(offb_set_mode); last_req = rospy.Time.now()
            else:
                if not self.current_state.armed and (rospy.Time.now() - last_req) > rospy.Duration(5.0):
                    self.arming_client.call(arm_cmd); last_req = rospy.Time.now()

            twist = Twist()
            # 고도 유지 (P제어)
            twist.linear.z = 1.0 * (HOVER_HEIGHT - self.current_pose.pose.position.z)

            # 타겟 감지 여부 확인
            if (rospy.Time.now().to_sec() - self.last_detection_time) < LOST_TIMEOUT:
                if not self.is_chasing: 
                    self.is_chasing = True
                    print("!!! 타겟 발견! 추적 모드 전환 !!!")
                self.chase_logic(twist)
            else:
                if self.is_chasing: 
                    self.is_chasing = False
                    print("...타겟 놓침. 순찰 모드 복귀...")
                self.patrol_logic(twist)

            self.vel_pub.publish(twist)
            rate.sleep()

    def chase_logic(self, twist):
        # 1. 회전 제어 (Yaw)
        error = 0.5 - self.target_info.x
        # P제어만 사용 (단순화)
        yaw_speed = PID_YAW[0] * error 
        twist.angular.z = np.clip(yaw_speed, -1.0, 1.0)

        # 2. 거리 제어 (Linear X)
        area = self.target_info.z
        fb_speed = 0

        # 면적이 너무 크면(가까우면) -> 후진
        if area > TARGET_AREA_RANGE[1]: 
            fb_speed = -0.3 # 천천히 후진
        # 면적이 너무 작으면(멀면) -> 전진
        elif area < TARGET_AREA_RANGE[0]: 
            fb_speed = CHASE_SPEED
        # 적당하면 -> 정지 (0)
        else:
            fb_speed = 0

        # 드론이 바라보는 방향으로 전진/후진
        yaw = self.get_current_yaw()
        twist.linear.x = fb_speed * math.cos(yaw)
        twist.linear.y = fb_speed * math.sin(yaw)

    def patrol_logic(self, twist):
        # 제자리 회전하며 주변 탐색
        twist.angular.z = PATROL_TURN_RATE
        twist.linear.x = 0
        twist.linear.y = 0

if __name__ == "__main__":
    try: PatrolChaseNode().run()
    except: pass
