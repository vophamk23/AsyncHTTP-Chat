"""
apps.sampleapp
~~~~~~~~~~~~~~~~~

Module này cung cấp một ứng dụng web mẫu sử dụng framework AsynapRous.
Định nghĩa các route handler cơ bản và khởi động TCP server để phục vụ HTTP request.

Cách dùng:
    >>> from apps.sampleapp import create_sampleapp
    >>> create_sampleapp("127.0.0.1", 9000)
"""

import json
import os
import sys

# Thêm thư mục gốc vào sys.path để import được daemon.*
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from daemon.asynaprous import AsynapRous

# Khởi tạo đối tượng app ở cấp module để các decorator @app.route() hoạt động đúng
app = AsynapRous()


@app.route("/", methods=["GET"])
def home(_):
    """Trang chủ – chào mừng người dùng."""
    return json.dumps({"message": "Welcome to the RESTful TCP WebApp"}).encode("utf-8")


@app.route("/user", methods=["GET"])
def get_user(_):
    """Trả về thông tin người dùng mẫu."""
    return json.dumps({"id": 1, "name": "Alice", "email": "alice@example.com"}).encode("utf-8")


@app.route("/echo", methods=["POST"])
def echo(req):
    """Nhận JSON từ client và trả lại đúng dữ liệu đó (Echo)."""
    try:
        data = json.loads(req.body)
        return json.dumps({"received": data}).encode("utf-8")
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON"}).encode("utf-8")


def create_sampleapp(ip, port):
    """
    Điểm khởi động ứng dụng mẫu AsynapRous.

    :param ip   (str): Địa chỉ IP để bind server.
    :param port (int): Số cổng lắng nghe.
    """
    app.prepare_address(ip, port)
    app.run()
