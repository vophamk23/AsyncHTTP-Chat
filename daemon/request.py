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
daemon.request
~~~~~~~~~~~~~~~~~

Module này cung cấp đối tượng Request để quản lý và duy trì
các thiết lập của một yêu cầu HTTP (cookies, xác thực, proxies).
"""
from .dictionary import CaseInsensitiveDict
import json as json_lib
from urllib.parse import urlparse, parse_qs

class Request():
    """Đối tượng :class:`Request <Request>` có khả năng thay đổi toàn diện,
    chứa chính xác các byte sẽ được gửi (hoặc đã nhận) đến/từ máy chủ.

    Các phiên bản (instances) được sinh ra từ đối tượng :class:`Request <Request>`,
    và không nên tự tạo thủ công; làm như vậy có thể gây ra những hậu quả không mong muốn.

    Ví dụ sử dụng (Usage)::

      >>> import daemon.request
      >>> req = request.Request()
      ## Lấy tin nhắn gửi đến (incoming_msg)
      >>> req.prepare(incoming_msg)
      >>> req
      <Request>
    """
    __attrs__ = [
        "method",
        "url",
        "headers",
        "body",
        "_raw_headers",
        "_raw_body",
        "reason",
        "cookies",
        "body",
        "routes",
        "hook",
        "query_params", # Đã bổ sung để hỗ trợ query string URL
    ]

    def __init__(self):
        #: Phương thức HTTP (GET, POST, PUT...).
        self.method = None
        #: Địa chỉ URL HTTP mà yêu cầu nhắm tới.
        self.url = None
        #: Từ điển (dictionary) chứa các HTTP headers.
        self.headers = None
        #: Đường dẫn HTTP (HTTP path).
        self.path = None        
        #: Bộ cookie được dùng để tạo header Cookie.
        self.cookies = None
        #: Nội dung yêu cầu (body) gửi tới máy chủ.
        self.body = None
        #: Raw headers (chuỗi chưa phân tích).
        self._raw_headers = None
        #: Raw body (nội dung chưa phân tích).
        self._raw_body = None
        #: Các định tuyến (Routes).
        self.routes = {}
        #: Điểm gắn kết (Hook point) cho các đường dẫn đã được định tuyến.
        self.hook = None
        #: Tham số truy vấn (ví dụ: ?user=A) - Cải tiến thực tế
        self.query_params = {}

    def extract_request_line(self, request):
        """Phân tích dòng đầu tiên của yêu cầu HTTP (request line)."""
        try:
            lines = request.splitlines()
            first_line = lines[0]
            method, raw_path, version = first_line.split()

            # Phân giải query_params để Web Chat P2P hoạt động
            parsed = urlparse(raw_path)  
            path = parsed.path  

            if path == '/':
                path = '/index.html'
                
            self.query_params = {
                k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()
            }
        except Exception:
            return None, None, None

        return method, path, version
             
    def prepare_headers(self, request):
        """Chuẩn bị và phân tích các HTTP headers được cung cấp."""
        lines = request.split('\r\n')
        headers = {}
        for line in lines[1:]:
            if ': ' in line:
                key, val = line.split(': ', 1)
                headers[key.lower()] = val
        return headers

    def fetch_headers_body(self, request):
        """Phân chia yêu cầu thành phần Header và phần Body."""
        # Cắt yêu cầu (request) tại khoảng trắng kép (blank line)
        parts = request.split("\r\n\r\n", 1) 

        _headers = parts[0]
        _body = parts[1] if len(parts) > 1 else ""
        return _headers, _body

    def prepare(self, request, routes=None):
        """Chuẩn bị toàn bộ yêu cầu (request) với các tham số cung cấp sẵn."""

        # Trích xuất dòng Request line từ header của yêu cầu
        print("[Request] Đang chuẩn bị (prepare) request msg...")
        self.method, self.path, self.version = self.extract_request_line(request)
        print("[Request] {} path {} version {}".format(self.method, self.path, self.version))

        # Phân tích headers
        self.headers = self.prepare_headers(request)

        #
        # @bksysnet Chuẩn bị hook của webapp với instance AsynapRous.
        # Hành vi mặc định của máy chủ HTTP là định tuyến rỗng.
        #
        # Đã giải quyết TODO: Quản lý webapp hook ở điểm gắn kết này.
        #
        if routes is not None and routes != {}:
            self.routes = routes
            print("[Request] Đang định tuyến METHOD {} path {}".format(self.method, self.path))
            self.hook = routes.get((self.method, self.path))
            print("[Request] Hook xử lý yêu cầu (request) hiện tại: {}".format(self.hook))
            #
            # Các thao tác tùy chỉnh cho self.hook đã được framework AsynapRous 
            # tự động liên kết bằng decorator @app.route()
            #

        # Lấy header và body thô
        self._raw_headers, self._raw_body = self.fetch_headers_body(request)

        # Đã giải quyết TODO: Triển khai chức năng cookie tại đây bằng cách phân tích header
        cookies_string = self.headers.get('cookie', '')
        self.cookies = {}
        if cookies_string:
            cookie_pairs = cookies_string.split("; ")  
            for pair in cookie_pairs:
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    self.cookies[name.strip()] = value

        return

    def prepare_body(self, data, files, json=None):
        """Cấu trúc phần thân (body) của yêu cầu."""
        body = b""
        if json is not None:
            body = json_lib.dumps(json).encode("utf-8")
            if self.headers is None: self.headers = {}
            self.headers["Content-Type"] = "application/json"
        elif data is not None:
            body = data if isinstance(data, bytes) else str(data).encode("utf-8")
        elif files is not None:
            combined = b""
            for f in files:
                combined += f.read() if isinstance(f.read(), bytes) else f.read().encode()
            body = combined
            
        self.body = body
        self.prepare_content_length(self.body)
        
        #
        # TODO chuẩn bị phương thức xác thực (authentication) cho yêu cầu
        #
        # self.auth = ...
        return

    def prepare_content_length(self, body):
        """Cấu hình độ dài nội dung (Content-Length)."""
        if self.headers is None: self.headers = {}
        self.headers["Content-Length"] = str(len(body)) if body else "0"
        
        #
        # TODO chuẩn bị phương thức xác thực (authentication) cho yêu cầu
        #
        # self.auth = ...
        return

    def prepare_auth(self, auth, url=""):
        """Chuẩn bị thiết lập xác thực."""
        #
        # TODO chuẩn bị phương thức xác thực (authentication) cho yêu cầu
        #
        # self.auth = ...
        return

    def prepare_cookies(self, cookies):
        """Thiết lập các cookies vào header."""
        if self.headers is None: self.headers = {}
        self.headers["Cookie"] = cookies
