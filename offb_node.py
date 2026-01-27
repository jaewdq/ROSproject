#! /usr/bin/env python3

import rospy
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest

current_state = State()

def state_cb(msg):
    global current_state
    current_state = msg

if __name__ == "__main__":
    rospy.init_node("offb_node_py")

    # 1. 상태 구독 및 위치 명령 발행
    state_sub = rospy.Subscriber("mavros/state", State, callback = state_cb)
    local_pos_pub = rospy.Publisher("mavros/setpoint_position/local", PoseStamped, queue_size=10)

    # 2. 시동(Arming) 및 모드 변경(SetMode) 서비스 클라이언트 설정
    rospy.wait_for_service("mavros/cmd/arming")
    arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)

    rospy.wait_for_service("mavros/set_mode")
    set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)

    # 3. 통신 주기 설정 (20Hz 권장)
    rate = rospy.Rate(20)

    # 4. FCU(비행제어장치) 연결 대기
    while(not rospy.is_shutdown() and not current_state.connected):
        rate.sleep()

    rospy.loginfo("Connected!")

    # 5. 목표 위치 설정 (x=0, y=0, z=2)
    pose = PoseStamped()
    pose.pose.position.x = 0
    pose.pose.position.y = 0
    pose.pose.position.z = 2

    # 6. Offboard 모드 진입 전, 미리 위치 신호를 100번 정도 보내야 함 (필수 안전 절차)
    for i in range(100):   
        if(rospy.is_shutdown()):
            break
        local_pos_pub.publish(pose)
        rate.sleep()

    # 7. 모드 변경 및 시동 요청 메시지 생성
    offb_set_mode = SetModeRequest()
    offb_set_mode.custom_mode = 'OFFBOARD'

    arm_cmd = CommandBoolRequest()
    arm_cmd.value = True

    last_req = rospy.Time.now()

    # 8. 메인 루프 (무한 반복)
    while(not rospy.is_shutdown()):
        # (A) 5초마다 상태 확인: OFFBOARD 모드가 아니면 모드 변경 시도
        if(current_state.mode != "OFFBOARD" and (rospy.Time.now() - last_req) > rospy.Duration(5.0)):
            if(set_mode_client.call(offb_set_mode).mode_sent == True):
                rospy.loginfo("OFFBOARD enabled")
            last_req = rospy.Time.now()
        else:
            # (B) 5초마다 상태 확인: 시동이 꺼져있으면 시동 걸기 시도
            if(not current_state.armed and (rospy.Time.now() - last_req) > rospy.Duration(5.0)):
                if(arming_client.call(arm_cmd).success == True):
                    rospy.loginfo("Vehicle armed")
                last_req = rospy.Time.now()

        # (C) 목표 위치 계속 전송 (이게 끊기면 드론이 멈추거나 착륙함)
        local_pos_pub.publish(pose)

        rate.sleep()
