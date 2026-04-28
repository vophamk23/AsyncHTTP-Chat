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
daemon.utils
~~~~~~~~~~~~

Module này chứa các hàm tiện ích (utilities) dùng chung cho hệ thống,
nhằm hỗ trợ xử lý và phân tách các thành phần trong chuỗi URL.
"""

# Chú ý: Ở Python 3, thư viện urlparse đã được chuyển vào urllib.parse.
# Cần import thêm 'unquote' để giải mã các ký tự đặc biệt trong URL.
from urllib.parse import urlparse, unquote

def get_auth_from_url(url):
    """
    Hàm tiện ích nhận vào một chuỗi URL có chứa các thành phần xác thực
    và trích xuất chúng thành một bộ giá trị (tuple) gồm (username, password).

    Ví dụ URL đầu vào: "http://admin:secret123@example.com/api"
    Kết quả trả về: ("admin", "secret123")

    :kiểu trả về (rtype): (str, str)
    """
    parsed = urlparse(url)

    try:
        # Giải mã các ký tự phần trăm (%) trong tên người dùng và mật khẩu
        auth = (unquote(parsed.username), unquote(parsed.password))
    except (AttributeError, TypeError):
        # Nếu URL không chứa thông tin đăng nhập, trả về chuỗi rỗng
        auth = ("", "")

    return auth
