#!/usr/bin/env python3

import re
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def normalize_target(text: str):
    if text is None:
        return None

    raw = text.strip().upper()
    raw = raw.replace('_', '-')
    raw = raw.replace(' ', '')

    m = re.fullmatch(r'([AB])-?([12])', raw)
    if m:
        return f'{m.group(1)}-{m.group(2)}'

    return None


class TerminalTargetSender(Node):
    def __init__(self):
        super().__init__('terminal_target_sender')

        self.target_pub = self.create_publisher(String, '/mission_target_name', 10)
        self.status_sub = self.create_subscription(
            String,
            '/mission_status_text',
            self.status_callback,
            10
        )

        self.latest_status = 'WAITING_FOR_COMMAND'
        self.get_logger().info('Terminal target sender started')

    def status_callback(self, msg: String):
        self.latest_status = msg.data
        print(f'\n[STATUS] {msg.data}')

    def publish_target(self, target_name: str):
        msg = String()
        msg.data = target_name
        self.target_pub.publish(msg)
        self.get_logger().info(f'Published target: {msg.data}')


def input_loop(node: TerminalTargetSender):
    print('==============================')
    print('입력 가능한 목표: A-1, A-2, B-1, B-2')
    print('예시 입력: A-1  또는  a1')
    print('종료하려면 quit 입력')
    print('==============================')

    while rclpy.ok():
        try:
            text = input('\n목표 지점을 입력하세요: ').strip()
        except EOFError:
            break

        if not text:
            continue

        if text.lower() in ['quit', 'exit', 'q']:
            break

        target = normalize_target(text)
        if target is None:
            print('[WARN] 잘못된 입력입니다. 예: A-1, A-2, B-1, B-2')
            continue

        node.publish_target(target)


def main(args=None):
    rclpy.init(args=args)
    node = TerminalTargetSender()

    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    try:
        input_loop(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
