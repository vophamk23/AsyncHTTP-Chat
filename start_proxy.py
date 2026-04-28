#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#

"""
start_proxy.py – Khởi động máy chủ Reverse Proxy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Module này là điểm khởi đầu để chạy Máy chủ Reverse Proxy,
tích hợp thuật toán cân bằng tải (Load Balancing) thông minh.

Chức năng chính:
- Đọc tệp cấu hình (config/proxy.conf) để lấy thông tin các miền ảo (virtual hosts).
- Phân tích các khối 'host' để xây dựng Bản đồ Định tuyến (Routing Table).
- Khởi động máy chủ Proxy tại địa chỉ IP và Cổng mạng cấu hình.

Cách Proxy hoạt động:
- Tiếp nhận yêu cầu HTTP từ phía Client.
- Quét Bản đồ Định tuyến để tìm danh sách Backend phù hợp cho tên miền được yêu cầu.
- Áp dụng thuật toán "Round-robin" để luân chuyển kết nối, tránh quá tải một máy chủ.
- Chuyển tiếp (forward) yêu cầu và hoàn trả dữ liệu lại cho Client.

Cách khởi động:
    python start_proxy.py --server-ip 127.0.0.1 --server-port 8080
"""

import socket
import threading
import argparse
import re

# from urlparse import urlparse
from urllib.parse import urlparse
from collections import defaultdict

from daemon import create_proxy

# Cong mac dinh cho proxy server (co the ghi de bang --server-port)
PROXY_PORT = 8888


def parse_virtual_hosts(config_file):
    """
    Doc va phan tich file cau hinh proxy (dinh dang tuong tu NGINX).

    Ham nay tim tat ca khoi 'host' trong file .conf,
    sau do xay dung bang dinh tuyen (routes) dang:
        { "ten_host": (["backend1", "backend2"], "chinh-sach") }

    :config_file (str): Duong dan den file cau hinh proxy.
    :rtype dict: Bang dinh tuyen { host_name: (backend_list, policy) }
    """

    with open(config_file, "r") as f:
        config_text = f.read()

    # Match each host block
    host_blocks = re.findall(r'host\s+"([^"]+)"\s*\{(.*?)\}', config_text, re.DOTALL)

    dist_policy_map = ""

    routes = {}
    for host, block in host_blocks:
        proxy_map = {}

        # Find all proxy_pass entries
        proxy_passes = re.findall(r"proxy_pass\s+http://([^\s;]+);", block)
        map = proxy_map.get(host, [])
        map = map + proxy_passes
        proxy_map[host] = map

        # Find dist_policy if present
        policy_match = re.search(
            r"dist_policy\s+([\w-]+)", block
        )  # Fix: error extract policy [Ly]
        if policy_match:
            dist_policy_map = policy_match.group(1)
        else:  # default policy is round_robin
            dist_policy_map = "round-robin"

        #
        # @bksysnet: Build the mapping and policy
        # TODO: this policy varies among scenarios
        #       the default policy is provided with one proxy_pass
        #       In the multi alternatives of proxy_pass then
        #       the policy is applied to identify the highes matching
        #       proxy_pass
        #
        if len(proxy_map.get(host, [])) == 1:
            routes[host] = (proxy_map.get(host, [])[0], dist_policy_map)
        # esle if:
        #         TODO:  apply further policy matching here
        #
        else:
            routes[host] = (proxy_map.get(host, []), dist_policy_map)

    for key, value in routes.items():
        print(key, value)  # In ra bang dinh tuyen de kiem tra khi khoi dong
    return routes


if __name__ == "__main__":
    """
    Diem vao chinh de khoi dong Proxy Server.

    Luong thuc thi:
    1. Phan tich tham so dong lenh (--server-ip, --server-port)
    2. Doc file config/proxy.conf -> xay dung routing table
    3. Goi create_proxy(ip, port, routes) -> khoi dong proxy

    Tham so:
        --server-ip   (str): Dia chi IP cho proxy. Mac dinh: 0.0.0.0
        --server-port (int): So cong cho proxy.   Mac dinh: 8080
    """

    parser = argparse.ArgumentParser(
        prog="Proxy", description="", epilog="Proxy daemon"
    )
    parser.add_argument("--server-ip", default="0.0.0.0")
    parser.add_argument("--server-port", type=int, default=PROXY_PORT)

    args = parser.parse_args()
    ip = args.server_ip  # Dia chi IP proxy
    port = args.server_port  # Cong proxy

    # Doc file cau hinh va xay dung bang dinh tuyen
    routes = parse_virtual_hosts("config/proxy.conf")

    # Khoi dong proxy server voi routing table da xay dung
    create_proxy(ip, port, routes)
