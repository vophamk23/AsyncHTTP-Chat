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
daemon.proxy
~~~~~~~~~~~~~~~~~

Module này hiện thực proxy server đơn giản bằng thư viện socket và threading.
Nó nhận yêu cầu HTTP từ client, định tuyến chúng đến các dịch vụ backend
dựa trên ánh xạ hostname, và trả kết quả phản hồi tương ứng về cho client.

Yêu cầu (Requirement):
-----------------
- socket: cung cấp giao diện giao tiếp mạng.
- threading: cho phép xử lý nhiều client đồng thời thông qua các luồng.
- response: cung cấp các tiện ích tùy chỉnh :class: `Response <Response>`.
- httpadapter: cung cấp bộ chuyển đổi :class: `HttpAdapter <HttpAdapter>` để xử lý request HTTP.
- dictionary: cung cấp :class: `CaseInsensitiveDict <CaseInsensitiveDict>` để quản lý headers và cookies.
"""
import socket
import threading
from .response import *
from .httpadapter import HttpAdapter
from .dictionary import CaseInsensitiveDict

#: Từ điển ánh xạ hostname tới bộ giá trị (tuple) IP và port của backend.
#: Được dùng để xác định mục tiêu định tuyến cho các yêu cầu gửi đến.
PROXY_PASS = {
    "192.168.56.103:8080": ("192.168.56.103", 9000),
    "app1.local": ("192.168.56.103", 9001),
    "app2.local": ("192.168.56.103", 9002),
}

# (Bổ sung phần đã giải quyết TODO load-balancing)
rr_counter = {}
rr_lock = threading.Lock()


def forward_request(host, port, request):
    """
    Chuyển tiếp yêu cầu HTTP tới máy chủ backend và nhận phản hồi.

    :params host (str): Địa chỉ IP của máy chủ backend.
    :params port (int): Số hiệu cổng của máy chủ backend.
    :params request (str): Yêu cầu HTTP gửi đến.

    :rtype bytes: Phản hồi HTTP thô (Raw) từ máy chủ backend. Nếu kết nối
                  thất bại, trả về phản hồi lỗi 404 Not Found.
    """

    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        backend.connect((host, port))
        backend.sendall(request.encode())
        response = b""
        while True:
            chunk = backend.recv(4096)
            if not chunk:
                break
            response += chunk
        return response
    except socket.error as e:
        print("Lỗi Socket (Socket error): {}".format(e))
        return (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 13\r\n"
            "Connection: close\r\n"
            "\r\n"
            "404 Not Found"
        ).encode("utf-8")


def resolve_routing_policy(hostname, routes):
    """
    Xử lý chính sách định tuyến để trả về proxy_pass phù hợp.
    Hàm này quyết định xem yêu cầu sẽ được chuyển tiếp đến backend nào.
    (Đã được hoàn thiện các khối TODO Load-balancing)

    :params hostname (str): Tên miền (hostname) từ yêu cầu của client.
    :params routes (dict): Từ điển ánh xạ hostname tới vị trí đích.
    """

    print(hostname)
    proxy_map, policy = routes.get(hostname, ("127.0.0.1:9000", "round-robin"))
    print(proxy_map)
    print(policy)

    proxy_host = ""
    proxy_port = "9000"
    if isinstance(proxy_map, list):
        if len(proxy_map) == 0:
            print("[Proxy] Danh sách định tuyến rỗng cho hostname {}".format(hostname))
            print("Kết quả proxy_map trống")
            # Giải quyết TODO: Xử lý lỗi khi hostname không được ánh xạ.
            # Dùng địa chỉ dummy để đánh dấu kết nối không hợp lệ.
            proxy_host = "127.0.0.1"
            proxy_port = "9000"
        elif len(proxy_map) == 1:
            # Sửa lỗi đánh máy trong source gốc (len(value) -> len(proxy_map))
            proxy_host, proxy_port = proxy_map[0].split(":", 2)
        else:
            # Giải quyết TODO: Áp dụng chính sách xử lý load-balancing (Round-robin)
            if policy == "round-robin":
                with rr_lock:
                    index = rr_counter.get(hostname, 0)
                    rr_counter[hostname] = (index + 1) % len(proxy_map)
                    backend = proxy_map[index]
                proxy_host, proxy_port = backend.split(":", 2)
            else:
                # Xử lý các trường hợp máy chủ đích nằm ngoài khả năng
                proxy_host = "127.0.0.1"
                proxy_port = "9000"
    else:
        print(
            "[Proxy] Định tuyến của hostname {} là điểm đích đơn lẻ (singular)".format(
                hostname
            )
        )
        proxy_host, proxy_port = proxy_map.split(":", 2)

    return proxy_host, proxy_port


def handle_client(ip, port, conn, addr, routes):
    """
    Xử lý một kết nối client độc lập bằng cách phân tích request,
    xác định backend đích, và chuyển tiếp yêu cầu đi.

    Hàm này trích xuất header 'Host' từ request để
    khớp hostname với bảng định tuyến. Dựa vào điều kiện khớp,
    nó sẽ chuyển tiếp yêu cầu tới backend phù hợp.

    Cuối cùng, hàm sẽ gửi lại kết quả từ backend cho client
    hoặc trả về lỗi 404 nếu không kết nối được / không nhận diện được.

    :params ip (str): Địa chỉ IP của máy chủ proxy.
    :params port (int): Cổng của máy chủ proxy.
    :params conn (socket.socket): Socket kết nối của client.
    :params addr (tuple): Địa chỉ client (IP, port).
    :params routes (dict): Bảng định tuyến ánh xạ hostname tới đích.
    """

    request = conn.recv(4096).decode()
    hostname = ""
    # Trích xuất hostname
    for line in request.splitlines():
        if line.lower().startswith("host:"):
            hostname = line.split(":", 1)[1].strip()

    print("[Proxy] {} tại Host: {}".format(addr, hostname))

    # Tìm kiếm điểm đến tương ứng trong routes và chuyển port sang kiểu số nguyên
    resolved_host, resolved_port = resolve_routing_policy(hostname, routes)
    try:
        resolved_port = int(resolved_port)
    except ValueError:
        print("Không phải số nguyên hợp lệ")

    if resolved_host:
        print(
            "[Proxy] Hostname {} được chuyển tiếp tới {}:{}".format(
                hostname, resolved_host, resolved_port
            )
        )
        response = forward_request(resolved_host, resolved_port, request)
    else:
        response = (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 13\r\n"
            "Connection: close\r\n"
            "\r\n"
            "404 Not Found"
        ).encode("utf-8")
    conn.sendall(response)
    conn.close()


def run_proxy(ip, port, routes):
    """
    Khởi động máy chủ proxy và lắng nghe các kết nối tới.

    Tiến trình này bind máy chủ proxy vào IP và cổng được chỉ định.
    Với mỗi kết nối gửi tới, nó sẽ chấp nhận và sinh ra (spawn)
    một luồng (thread) mới cho mỗi client sử dụng hàm `handle_client`.

    :params ip (str): Địa chỉ IP để bind máy chủ proxy.
    :params port (int): Cổng để lắng nghe.
    :params routes (dict): Từ điển ánh xạ hostname tới vị trí đích.
    """

    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        proxy.bind((ip, port))
        proxy.listen(50)
        print("[Proxy] Đang lắng nghe trên IP {} cổng {}".format(ip, port))
        while True:
            conn, addr = proxy.accept()
            #
            #  Đã giải quyết TODO: Triển khai các bước tiếp nhận kết nối client mới
            #                      bằng lập trình đa luồng (multi-thread) với
            #                      hàm handle_client được cung cấp.
            #
            client_thread = threading.Thread(
                target=handle_client, args=(ip, port, conn, addr, routes)
            )
            client_thread.start()

    except socket.error as e:
        print("Lỗi Socket (Socket error): {}".format(e))


def create_proxy(ip, port, routes):
    """
    Điểm vào (Entry point) để khởi chạy máy chủ proxy.

    :params ip (str): Địa chỉ IP để bind máy chủ proxy.
    :params port (int): Cổng để lắng nghe.
    :params routes (dict): Từ điển ánh xạ hostname.
    """

    run_proxy(ip, port, routes)
