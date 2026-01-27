#! /usr/bin/env python3

import rospy
import cv2
from sensor_msgs.msg import Image
from geometry_msgs.msg import Point
from cv_bridge import CvBridge, CvBridgeError
from ultralytics import YOLO
#class 명 지정하고 뭐 받아올지 고민 여기 model 
class YoloTracker:
    def __init__(self):
        rospy.init_node('yolo_tracker_node', anonymous=True)
        
        # 모델 로드
        self.model = YOLO('yolov8n.pt')
        self.bridge = CvBridge()
        self.frame_count = 0

        # 토픽 확인 (아까 확인한 주소)
        self.image_sub = rospy.Subscriber("/iris0/usb_cam/image_raw", Image, self.image_callback)
        self.target_pub = rospy.Publisher("/tracker/target_pos", Point, queue_size=1)
        
        rospy.loginfo("============ 디버깅 모드 시작 ============")
        rospy.loginfo("이미지가 들어오면 터미널에 메시지가 뜹니다.")

    def image_callback(self, msg):
        # 1. 이미지 수신 확인용 로그 (너무 많이 뜨면 주석 처리)
        # print("DEBUG: Image Received") 

        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except CvBridgeError as e:
            print(f"Error: {e}")
            return

        # 2. YOLO 추론 (conf를 0.1로 극한까지 낮춤)
        # 모든 클래스 탐지, 확신도 10%만 넘으면 다 잡음
        results = self.model(cv_image, verbose=False, conf=0.50)

        # 3. 결과 분석
        det_count = len(results[0].boxes)
        
        # 감지된 게 없으면 없다고 출력 (이게 중요!)
        if det_count == 0:
            print(">> 감지 실패 (화면에 물체가 없거나 인식 불가)")
            # 화면은 계속 띄워줌
            cv2.imshow("UAV0 Sight (DEBUG)", cv_image)
            cv2.waitKey(1)
            return

        # 감지된 게 있으면
        print(f"!!! {det_count}개 물체 감지됨 !!!")
        
        target_msg = Point(z=0.0)
        
        # 첫 번째 물체 정보 가져오기
        box = results[0].boxes[0]
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        area = (x2 - x1) * (y2 - y1)

        # 메시지 생성
        height, width, _ = cv_image.shape
        target_msg.x = center_x / width
        target_msg.y = center_y / height
        target_msg.z = area

        # 화면에 박스 그리기
        cv2.rectangle(cv_image, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        
        # 이름 출력
        cls_id = int(box.cls[0])
        name = self.model.names[cls_id]
        conf = float(box.conf[0])
        label = f"{name} {conf*100:.1f}%"
        cv2.putText(cv_image, label, (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

        self.target_pub.publish(target_msg)
        
        # 4. 화면 띄우기
        cv2.imshow("UAV0 Sight (DEBUG)", cv_image)
        cv2.waitKey(1)

if __name__ == '__main__':
    detector = YoloTracker()
    try:
        rospy.spin()
    except KeyboardInterrupt:
        pass
    cv2.destroyAllWindows()