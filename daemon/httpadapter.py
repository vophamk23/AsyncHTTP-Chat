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
daemon.httpadapter
~~~~~~~~~~~~~~~~~

Module này đóng vai trò là "Bộ chuyển đổi lõi" (Core Adapter) của hệ thống.
Nhiệm vụ của nó là tiếp nhận các luồng byte thô (raw bytes) từ máy chủ mạng (Backend),
giải mã chúng thành thông tin HTTP có ý nghĩa (Headers, Body, Cookies), và sau đó 
quyết định xem nên giao yêu cầu này cho AI/Logic xử lý (API Hooks) hay tự động 
trả về một tệp tĩnh (HTML/CSS/JS).
"""

from .request import Request
from .response import Response
from .dictionary import CaseInsensitiveDict

import asyncio
import inspect
import json


class HttpAdapter:
    """
    Lớp :class:`HttpAdapter <HttpAdapter>` - "Tổng chỉ huy" xử lý vòng đời một giao dịch HTTP.

    Nếu `backend.py` là người gác cổng đón khách, thì `HttpAdapter` chính là vị quản lý 
    bên trong nhà hàng. Khi một khách hàng (Client) đưa ra yêu cầu (Request):
    1. Quản lý sẽ đọc kỹ yêu cầu đó (Phân tích Header, Content-Length).
    2. Kiểm tra xem khách có vé VIP không (Bảo mật Cookie).
    3. Tra cứu sổ tay xem món này do đầu bếp nào nấu (Định tuyến API Hook).
    4. Nếu không phải món đặc biệt, tự động mang đồ ăn đóng hộp ra phục vụ (Trả về File tĩnh).

    Thuộc tính cốt lõi (Attributes):
        ip (str): Địa chỉ IP của khách hàng.
        port (int): Cổng mạng của khách hàng.
        conn (socket): Đường ống kết nối trực tiếp (socket).
        routes (dict): Bản đồ chỉ đường (Routes) để biết gọi hàm nào.
        request (Request): Kho lưu trữ thông tin yêu cầu của khách.
        response (Response): Kho lưu trữ thông điệp sẽ gửi trả lại khách.
    """

    __attrs__ = [
        "ip",
        "port",
        "conn",
        "connaddr",
        "routes",
        "request",
        "response",
    ]

    def __init__(self, ip, port, conn, connaddr, routes):
        """Khởi tạo một bộ điều phối HttpAdapter mới cho mỗi phiên làm việc."""
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes
        self.request = Request()
        self.response = Response()

    def handle_client(self, conn, addr, routes):
        """
        Quy trình xử lý Giao dịch Đồng bộ (Synchronous Pipeline).

        Đây là động cơ chính để đọc luồng dữ liệu TCP, bóc tách cấu trúc HTTP 
        theo tiêu chuẩn quốc tế (RFC) và điều phối bảo mật. Đoạn code này đã giải quyết 
        triệt để bài toán TODO của đồ án: Đọc đủ Content-Length và Chặn truy cập trái phép.

        :param conn (socket): Ống dẫn dữ liệu tới Client.
        :param addr (tuple): Tọa độ của Client.
        :param routes (dict): Bản đồ định tuyến API.
        """
        self.conn = conn        
        self.connaddr = addr
        req = self.request
        resp = self.response

        # -------------------------------------------------------------
        # BƯỚC 1: HÚT DỮ LIỆU TỪ ỐNG DẪN (ĐỌC HEADER)
        # -------------------------------------------------------------
        # Đặt thời gian chờ tối đa 2 giây để tránh bị treo (Deadlock)
        conn.settimeout(2)  
        raw = b""
        try:
            # Liên tục đọc cho đến khi gặp ranh giới '\r\n\r\n' (Kết thúc Header)
            while b"\r\n\r\n" not in raw:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
        except Exception:
            pass

        # Nếu khách hàng ngắt kết nối đột ngột
        if not raw:
            try: conn.close()
            except Exception: pass
            return

        # Bóc tách và giải mã văn bản Header
        header_end = raw.find(b"\r\n\r\n")
        header_bytes = raw[: header_end + 4] if header_end != -1 else raw
        header_text = header_bytes.decode("utf-8", errors="replace")

        # Nạp dữ liệu vào đối tượng Request để phân tích sâu (Method, URL, Cookies...)
        req.prepare(header_text, routes)
        print("[HttpAdapter] Đang xử lý giao dịch đồng bộ từ {}".format(addr))

        # -------------------------------------------------------------
        # BƯỚC 2: HÚT PHẦN THÂN YÊU CẦU (ĐỌC BODY)
        # -------------------------------------------------------------
        content_length = int(req.headers.get("content-length", 0))
        body = raw[header_end + 4 :] if header_end != -1 else b""
        to_read = content_length - len(body)
        
        # Nếu Body còn thiếu, tiếp tục hút cho đến khi đủ chỉ tiêu
        try:
            while to_read > 0:
                chunk = conn.recv(min(4096, to_read))
                if not chunk:
                    break
                body += chunk
                to_read -= len(chunk)
        except Exception:
            pass

        req.body = body.decode("utf-8", errors="replace")

        def send_and_close(data_bytes):
            """Hàm tiện ích nội bộ: Đẩy hàng qua ống dẫn và đóng nắp."""
            try: conn.sendall(data_bytes)
            except Exception: pass
            try: conn.close()
            except Exception: pass

        # -------------------------------------------------------------
        # BƯỚC 3: TRẠM KIỂM SOÁT AN NINH (BẢO MẬT COOKIE)
        # -------------------------------------------------------------
        # Các khu vực mở cửa tự do
        public_pages = ["/login.html", "/submit.html"]
        
        # Nếu truy cập vào các trang tĩnh (HTML) khác, phải xuất trình Thẻ VIP (Cookie auth=true)
        if req.method == "GET" and req.path.endswith(".html") and req.path not in public_pages:
            cookie_val = req.cookies.get("auth", "")
            is_auth = (cookie_val and cookie_val.split(";", 1)[0].strip() == "true")
            
            if not is_auth:
                # Trục xuất (Trả về lỗi 401 Unauthorized)
                send_and_close(resp.build_unauthorized())
                return
            
            # Nếu hợp lệ, phục vụ tệp HTML bình thường
            send_and_close(resp.build_response(req))
            return

        # -------------------------------------------------------------
        # BƯỚC 4: ĐIỀU PHỐI LOGIC VÀ TRẢ KẾT QUẢ (ROUTING / FALLBACK)
        # -------------------------------------------------------------
        # Nếu yêu cầu này khớp với một API Hook đã đăng ký (Ví dụ: /api/chat)
        if req.hook:
            try:
                # Bàn giao cho Hàm xử lý (Handler) thực thi
                api_response = req.hook(req)  
                send_and_close(api_response)
                return
            except Exception as e:
                # Nếu Hàm xử lý gặp lỗi, bung khiên bảo vệ 500 Internal Error
                err = json.dumps({"error": "Lỗi máy chủ nội bộ", "message": str(e)})
                response_bytes = (
                    "HTTP/1.1 500 Internal Server Error\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(err.encode('utf-8'))}\r\n"
                    "Connection: close\r\n\r\n" f"{err}"
                ).encode("utf-8")
                send_and_close(response_bytes)
                return

        # Fallback (Mặc định): Nếu không có Hook nào, tự động tìm và trả về file tĩnh (CSS, JS, Hình ảnh...)
        send_and_close(resp.build_response(req))
        return

    async def handle_client_coroutine(self, reader, writer):
        """
        Quy trình xử lý Giao dịch Bất đồng bộ (Asynchronous Pipeline).

        Phiên bản nâng cấp dùng Coroutine (thư viện Asyncio) để đọc/ghi dữ liệu
        mà không làm "kẹt" (block) tiến trình chính của máy chủ.

        :param reader: Luồng dữ liệu trôi vào (Stream reader).
        :param writer: Luồng dữ liệu trôi ra (Stream writer).
        """
        req = self.request
        resp = self.response
        addr = writer.get_extra_info("peername")
        print("[HttpAdapter] Đang xử lý giao dịch BẤT ĐỒNG BỘ từ {})".format(addr))

        # Đọc dữ liệu không chặn (Non-blocking read)
        msg = await reader.read(4096)
        if not msg:
            writer.close()
            return

        req.prepare(msg.decode("utf-8", errors="replace"), routes=self.routes)
        response = b""
        
        if req.hook:
            # Nhận diện thông minh: Hàm xử lý là Đồng bộ hay Bất đồng bộ?
            try:
                if inspect.iscoroutinefunction(req.hook):
                    # Nếu là Coroutine, phải dùng 'await' để đợi kết quả
                    response = await req.hook(req)
                else:
                    # Nếu là hàm thường, gọi chạy trực tiếp
                    response = req.hook(req)
            except Exception as e:
                response = b"HTTP/1.1 500 Internal Server Error\r\n\r\n"
        else:
            response = resp.build_response(req)

        # Bơm dữ liệu trả về mạng và xả luồng (drain)
        writer.write(response)
        await writer.drain()
        writer.close()

    @property
    def extract_cookies(self, req, resp):
        """Trích xuất và tinh chế các thẻ Cookie từ đống hỗn độn của Headers."""
        cookies = {}
        cookie_header = req.headers.get("cookie", "")
        if cookie_header:
            for pair in cookie_header.split(";"):
                try:
                    key, value = pair.strip().split("=")
                    cookies[key.strip()] = value.strip()
                except ValueError:
                    pass
        return cookies

    def build_response(self, req, resp):
        """Xây dựng khung xương (Skeleton) cho đối tượng Response."""
        response = Response()
        response.raw = resp
        response.reason = "OK"

        if isinstance(req.url, bytes):
            response.url = req.url.decode("utf-8")
        else:
            response.url = req.url

        response.cookies = self.extract_cookies(req, resp)
        response.request = req
        response.connection = self
        return response

    def build_json_response(self, req, resp):
        """Khung xương chuyên dụng để trả về dữ liệu chuẩn JSON."""
        response = Response(req)
        response.raw = resp
        if isinstance(req.url, bytes):
            response.url = req.url.decode("utf-8")
        else:
            response.url = req.url

        response.request = req
        response.connection = self
        return response

    def add_headers(self, request):
        """Điểm gắn kết (Hook) cho phép nhà phát triển tiêm thêm Headers tùy chỉnh."""
        pass

    def build_proxy_headers(self, proxy):
        """
        Xây dựng vũ khí vượt tường lửa (Proxy-Authorization Headers)
        khi hệ thống đóng vai trò là một Reverse Proxy.
        """
        headers = {}
        # Thông tin xác thực ảo phục vụ cho Demo
        username, password = ("user1", "password")

        if username:
            headers["Proxy-Authorization"] = (username, password)

        return headers
