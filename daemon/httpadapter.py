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
Nhiệm vụ của nó là tiếp nhận các luồng byte thô (raw bytes) từ kết nối TCP,
giải mã chúng thành thông tin HTTP có ý nghĩa (Headers, Body, Cookies), và sau đó
quyết định xem nên giao yêu cầu này cho logic xử lý (API Hooks) hay tự động
trả về một tệp tĩnh (HTML/CSS/JS/Image).
 
Luồng xử lý tổng quát:
    1. Đọc Header TCP cho đến khi gặp ranh giới CRLF kép (\\r\\n\\r\\n).
    2. Đọc Body dựa theo giá trị Content-Length trong Header.
    3. Kiểm tra xác thực Cookie (Auth Check).
    4. Định tuyến yêu cầu đến API Hook hoặc trả về file tĩnh (Fallback).
    5. Gửi phản hồi và đóng kết nối.
 
Hai chế độ hoạt động:
    - Đồng bộ  (Synchronous) : ``handle_client``          — dùng với ``socket`` + ``threading``.
    - Bất đồng bộ (Async)    : ``handle_client_coroutine`` — dùng với ``asyncio`` streams.
"""
 
from .request import Request
from .response import Response
from .dictionary import CaseInsensitiveDict
 
import asyncio
import inspect
import json
 
 
class HttpAdapter:
    """
    Bộ điều phối trung tâm cho một phiên giao dịch HTTP.
 
    Mỗi kết nối TCP đến từ client sẽ được bọc trong một instance ``HttpAdapter``
    riêng biệt. Class này chịu trách nhiệm toàn bộ vòng đời xử lý:
    đọc dữ liệu thô → phân tích HTTP → kiểm tra bảo mật → định tuyến → trả kết quả.
 
    Attributes:
        ip (str)              : Địa chỉ IP của máy chủ đang lắng nghe.
        port (int)            : Cổng mạng của máy chủ đang lắng nghe.
        conn (socket.socket)  : Socket kết nối tới client (có thể là None với async).
        connaddr (tuple)      : Địa chỉ (IP, port) của client đang kết nối.
        routes (dict)         : Bảng định tuyến dạng ``{(METHOD, path): handler_func}``.
        request (Request)     : Đối tượng lưu trữ thông tin yêu cầu HTTP đã phân tích.
        response (Response)   : Đối tượng chịu trách nhiệm xây dựng phản hồi HTTP.
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
        """
        Khởi tạo một HttpAdapter mới cho mỗi phiên kết nối.
 
        Args:
            ip (str)             : Địa chỉ IP máy chủ.
            port (int)           : Cổng máy chủ.
            conn (socket.socket) : Socket kết nối tới client.
            connaddr (tuple)     : Địa chỉ client dạng (ip, port).
            routes (dict)        : Bảng định tuyến API Hook.
        """
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes
        self.request = Request()
        self.response = Response()
 
    # ==========================================================================
    # XỬ LÝ ĐỒNG BỘ (SYNCHRONOUS) — Dùng với socket blocking + threading
    # ==========================================================================
 
    def handle_client(self, conn, addr, routes):
        """
        Pipeline xử lý giao dịch HTTP theo chế độ đồng bộ (blocking I/O).
 
        Hàm này được gọi từ một thread riêng biệt cho mỗi kết nối TCP đến.
        Toàn bộ quá trình đọc/ghi socket diễn ra tuần tự và chặn (blocking)
        cho đến khi hoàn tất hoặc hết thời gian chờ (timeout).
 
        Quy trình xử lý:
            1. Đọc Header liên tục cho đến khi gặp ``\\r\\n\\r\\n``.
            2. Đọc Body theo đúng ``Content-Length`` còn thiếu.
            3. Kiểm tra Cookie xác thực cho các trang HTML được bảo vệ.
            4. Gọi API Hook nếu path khớp, hoặc trả về file tĩnh (fallback).
 
        Args:
            conn (socket.socket) : Socket kết nối tới client.
            addr (tuple)         : Địa chỉ client dạng (ip, port).
            routes (dict)        : Bảng định tuyến API Hook.
        """
        self.conn = conn
        self.connaddr = addr
        req = self.request
        resp = self.response
 
        # ------------------------------------------------------------------
        # BƯỚC 1: ĐỌC HEADER
        # Đặt timeout 2 giây để tránh bị treo vô hạn (Deadlock) khi client
        # ngắt kết nối giữa chừng mà không gửi FIN.
        # Đọc từng chunk 4096 bytes và nối lại cho đến khi tìm thấy ranh giới
        # kết thúc Header theo chuẩn HTTP/1.1: \r\n\r\n
        # ------------------------------------------------------------------
        conn.settimeout(2)
        raw = b""
        try:
            while b"\r\n\r\n" not in raw:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
        except Exception:
            # Timeout hoặc lỗi socket — bỏ qua, xử lý ở bước kiểm tra bên dưới
            pass
 
        # Nếu không nhận được dữ liệu nào (client ngắt kết nối ngay), đóng và thoát
        if not raw:
            try:
                conn.close()
            except Exception:
                pass
            return
 
        # Tách phần Header khỏi phần Body dựa vào vị trí \r\n\r\n
        header_end = raw.find(b"\r\n\r\n")
        header_bytes = raw[: header_end + 4] if header_end != -1 else raw
        header_text = header_bytes.decode("utf-8", errors="replace")
 
        # Phân tích Header vào đối tượng Request (method, path, cookies, hook...)
        req.prepare(header_text, routes)
        print("[HttpAdapter] Đang xử lý giao dịch ĐỒNG BỘ từ {}".format(addr))
 
        # ------------------------------------------------------------------
        # BƯỚC 2: ĐỌC BODY
        # Tính số byte Body còn thiếu dựa vào Content-Length và phần Body
        # đã được đọc kèm theo Header ở bước trước.
        # Tiếp tục recv() cho đến khi đủ Content-Length hoặc socket đóng.
        # ------------------------------------------------------------------
        content_length = int(req.headers.get("content-length", 0))
        body = raw[header_end + 4 :] if header_end != -1 else b""
        to_read = content_length - len(body)
 
        try:
            while to_read > 0:
                # Đọc tối đa 4096 bytes hoặc số byte còn thiếu (tránh over-read)
                chunk = conn.recv(min(4096, to_read))
                if not chunk:
                    break
                body += chunk
                to_read -= len(chunk)
        except Exception:
            pass
 
        req.body = body.decode("utf-8", errors="replace")
 
        def send_and_close(data_bytes):
            """
            Hàm nội bộ: Gửi toàn bộ dữ liệu phản hồi rồi đóng socket.
 
            Bọc trong try/except để tránh crash khi client đã ngắt kết nối
            trước khi server kịp gửi phản hồi.
 
            Args:
                data_bytes (bytes): Dữ liệu HTTP response hoàn chỉnh cần gửi.
            """
            try:
                conn.sendall(data_bytes)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
 
        # ------------------------------------------------------------------
        # BƯỚC 3: KIỂM TRA XÁC THỰC (AUTH CHECK)
        # Chỉ áp dụng cho các request GET đến file .html không nằm trong
        # danh sách trang công khai (public_pages).
        # Yêu cầu cookie "auth=true" — nếu thiếu hoặc sai, trả về 401.
        # ------------------------------------------------------------------
        # Danh sách các trang HTML không yêu cầu xác thực
        public_pages = ["/login.html"]
 
        if (
            req.method == "GET"
            and req.path.endswith(".html")
            and req.path not in public_pages
        ):
            cookie_val = req.cookies.get("auth", "")
            # Lấy phần giá trị trước dấu ';' (vd: "true; Path=/") để so sánh
            is_auth = cookie_val and cookie_val.split(";", 1)[0].strip() == "true"
 
            if not is_auth:
                # Không có quyền truy cập — trả về 401 Unauthorized
                send_and_close(resp.build_unauthorized())
                return
 
            # Xác thực hợp lệ — phục vụ file HTML bình thường
            send_and_close(resp.build_response(req))
            return
 
        # ------------------------------------------------------------------
        # BƯỚC 4: ĐỊNH TUYẾN VÀ TRẢ KẾT QUẢ
        # Nếu path của request khớp với một API Hook đã được đăng ký
        # qua decorator @app.route(), gọi handler đó và trả kết quả.
        # Nếu không có Hook nào khớp, fallback về cơ chế phục vụ file tĩnh.
        # ------------------------------------------------------------------
        if req.hook:
            try:
                # Gọi handler function tương ứng với route đã đăng ký
                api_response = req.hook(req)
                send_and_close(api_response)
                return
            except Exception as e:
                # Lỗi trong handler — trả về 500 Internal Server Error với chi tiết lỗi
                err = json.dumps({"error": "Lỗi máy chủ nội bộ", "message": str(e)})
                response_bytes = (
                    "HTTP/1.1 500 Internal Server Error\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(err.encode('utf-8'))}\r\n"
                    "Connection: close\r\n\r\n"
                    f"{err}"
                ).encode("utf-8")
                send_and_close(response_bytes)
                return
 
        # Fallback: Không có Hook nào khớp — tìm và trả về file tĩnh tương ứng
        # (HTML, CSS, JS, hình ảnh...) dựa theo path và MIME type
        send_and_close(resp.build_response(req))
        return

    # ==========================================================================
    # XỬ LÝ BẤT ĐỒNG BỘ (ASYNCHRONOUS) — Dùng với asyncio streams
    # ==========================================================================
 
    async def handle_client_coroutine(self, reader, writer):
        """
        Pipeline xử lý giao dịch HTTP theo chế độ bất đồng bộ (non-blocking I/O).
 
        Hàm coroutine này được gọi bởi ``asyncio.start_server()`` cho mỗi kết nối
        TCP đến. Tất cả các thao tác I/O đều dùng ``await`` để nhường CPU cho
        event loop, tránh chặn (block) các kết nối đồng thời khác.
 
        Quy trình xử lý (tương tự ``handle_client`` nhưng bất đồng bộ):
            1. Đọc Header bất đồng bộ cho đến khi gặp ``\\r\\n\\r\\n``.
            2. Đọc Body bất đồng bộ theo đúng ``Content-Length`` còn thiếu.
            3. Kiểm tra Cookie xác thực cho các trang HTML được bảo vệ.
            4. Gọi API Hook (hỗ trợ cả sync và async hook), hoặc trả file tĩnh.
            5. Gửi phản hồi và đóng writer stream.
 
        Args:
            reader (asyncio.StreamReader) : Luồng đọc dữ liệu bất đồng bộ từ client.
            writer (asyncio.StreamWriter) : Luồng ghi dữ liệu bất đồng bộ tới client.
        """
        req = self.request
        resp = self.response
        addr = writer.get_extra_info("peername")
 
        print("[HttpAdapter] Đang xử lý giao dịch BẤT ĐỒNG BỘ từ {}".format(addr))
 
        raw = b""
 
        # ------------------------------------------------------------------
        # BƯỚC 1: ĐỌC HEADER (BẤT ĐỒNG BỘ)
        # Đọc từng chunk 1024 bytes và nối lại cho đến khi tìm thấy \r\n\r\n.
        # Dùng await để không chặn event loop trong khi chờ dữ liệu từ network.
        # ------------------------------------------------------------------
        try:
            while b"\r\n\r\n" not in raw:
                chunk = await reader.read(1024)
                if not chunk:
                    # Client đóng kết nối hoặc EOF
                    break
                raw += chunk
        except Exception:
            # Lỗi stream — đóng kết nối và thoát
            writer.close()
            return
 
        # Không nhận được dữ liệu nào — đóng kết nối
        if not raw:
            writer.close()
            return
 
        # Tách Header và phân tích vào đối tượng Request
        header_end = raw.find(b"\r\n\r\n")
        header_bytes = raw[: header_end + 4]
        header_text = header_bytes.decode("utf-8", errors="replace")
 
        req.prepare(header_text, routes=self.routes)
 
        # ------------------------------------------------------------------
        # BƯỚC 2: ĐỌC BODY (BẤT ĐỒNG BỘ)
        # Tính số byte Body còn thiếu và tiếp tục await reader.read()
        # cho đến khi đủ Content-Length.
        # ------------------------------------------------------------------
        content_length = int(req.headers.get("content-length", 0))
        body = raw[header_end + 4 :]
        to_read = content_length - len(body)
 
        try:
            while to_read > 0:
                # Đọc tối đa 1024 bytes hoặc số byte còn thiếu
                chunk = await reader.read(min(1024, to_read))
                if not chunk:
                    break
                body += chunk
                to_read -= len(chunk)
        except Exception:
            pass
 
        req.body = body.decode("utf-8", errors="replace")
 
        # ------------------------------------------------------------------
        # BƯỚC 3: KIỂM TRA XÁC THỰC (AUTH CHECK)
        # Logic tương tự handle_client: yêu cầu cookie "auth=true"
        # cho tất cả các trang HTML không nằm trong public_pages.
        # ------------------------------------------------------------------
        public_pages = ["/login.html"]
 
        if (
            req.method == "GET"
            and req.path.endswith(".html")
            and req.path not in public_pages
        ):
            cookie_val = req.cookies.get("auth", "")
            is_auth = cookie_val and cookie_val.split(";", 1)[0].strip() == "true"
 
            if not is_auth:
                # Không có quyền — trả về 401 Unauthorized và đóng stream
                writer.write(resp.build_unauthorized())
                await writer.drain()
                writer.close()
                return
 
        # ------------------------------------------------------------------
        # BƯỚC 4: ĐỊNH TUYẾN VÀ TRẢ KẾT QUẢ (BẤT ĐỒNG BỘ)
        # Hỗ trợ cả hai loại hook:
        #   - Coroutine function: dùng `await` để chờ kết quả
        #   - Regular function  : gọi trực tiếp (synchronous call)
        # Nếu không có hook nào khớp, fallback về file tĩnh.
        # ------------------------------------------------------------------
        if req.hook:
            try:
                if inspect.iscoroutinefunction(req.hook):
                    # Hook là async function — phải await để lấy kết quả
                    response = await req.hook(req)
                else:
                    # Hook là regular function — gọi trực tiếp
                    response = req.hook(req)
            except Exception as e:
                # Lỗi trong hook handler — trả về 500 với thông tin lỗi
                err = json.dumps({"error": str(e)})
                response = (
                    "HTTP/1.1 500 Internal Server Error\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(err.encode())}\r\n\r\n"
                    f"{err}"
                ).encode()
        else:
            try:
                # Fallback: Tìm và trả về file tĩnh tương ứng với path
                response = resp.build_response(req)
            except Exception as e:
                # Không tìm thấy file hoặc lỗi đọc file — trả về 500
                print(f"[Error] Không thể tải file tĩnh: {e}")
                response = b"HTTP/1.1 500 Internal Error\r\n\r\n"

        # ------------------------------------------------------------------
        # BƯỚC 5: GỬI PHẢN HỒI VÀ ĐÓNG KẾT NỐI
        # writer.drain() đảm bảo toàn bộ dữ liệu đã được flush xuống buffer
        # mạng trước khi đóng stream.
        # ------------------------------------------------------------------
        writer.write(response)
        await writer.drain()
        writer.close()