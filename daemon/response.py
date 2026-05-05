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
daemon.response
~~~~~~~~~~~~~~~~~

Module này hoạt động như một "Xưởng Đóng Gói" (Response Builder) của hệ thống.
Nhiệm vụ của nó là gom toàn bộ kết quả xử lý (File tĩnh, Dữ liệu JSON, Lỗi...),
xác định đúng loại bao bì (MIME type), dán nhãn vận chuyển (HTTP Headers),
và đóng gói thành một hộp hàng chuẩn chỉnh (HTTP Response) để gửi về cho khách hàng.
"""

import datetime
import os
import json
import mimetypes
from .dictionary import CaseInsensitiveDict

BASE_DIR = ""


class Response:
    """
    Lớp :class:`Response <Response>` - Đại diện cho một "Gói Hàng" hoàn chỉnh.

    Mỗi gói hàng này chứa đầy đủ thông tin:
    - Nhãn dán (Headers): Báo cho trình duyệt biết bên trong là gì.
    - Tem kiểm định (Status Code): Mã 200 (Thành công), 404 (Không tìm thấy)...
    - Quà tặng kèm (Cookies): Dùng để ghi nhớ người dùng cho lần sau.
    - Lõi sản phẩm (Body/Content): Hình ảnh, mã HTML, hoặc chuỗi JSON.
    """

    __attrs__ = [
        "_content",
        "_header",
        "status_code",
        "method",
        "headers",
        "url",
        "history",
        "encoding",
        "reason",
        "cookies",
        "elapsed",
        "request",
        "body",
        "reason",
    ]

    def __init__(self, request=None):
        """Tạo một Hộp Hàng rỗng, chuẩn bị cho quá trình đóng gói."""
        self._content = b""
        self._content_consumed = False
        self._next = None

        #: Mã trạng thái số nguyên (vd: 200, 401, 404, 500).
        self.status_code = None
        #: Từ điển chứa các nhãn dán Headers.
        self.headers = {}
        #: Đường dẫn URL của gói hàng.
        self.url = None
        #: Bảng mã (Encoding) dùng để giải mã nội dung.
        self.encoding = None
        #: Nhật ký vòng đời gói hàng.
        self.history = []
        #: Chú thích bằng chữ cho mã trạng thái (vd: "OK", "Not Found").
        self.reason = None
        #: Giỏ chứa Cookies, được cấu trúc tự động để không phân biệt HOA/thường.
        self.cookies = CaseInsensitiveDict()
        #: Thời gian tiêu tốn để chuẩn bị gói hàng này.
        self.elapsed = datetime.timedelta(0)
        #: Giữ lại bản sao tờ đơn yêu cầu (Request) ban đầu.
        self.request = None

    def get_mime_type(self, path):
        """Máy quét phân loại: Đoán xem file thuộc loại gì (MIME type) dựa vào đuôi mở rộng."""
        try:
            mime_type, _ = mimetypes.guess_type(path)
        except Exception:
            return "application/octet-stream"

        # Xử lý đặc quyền cho Logo trang web (Favicon)
        if path.endswith(".ico"):
            return "image/x-icon"

        return mime_type or "application/octet-stream"

    def prepare_content_type(self, mime_type="text/html"):
        """
        Quyết định loại bao bì (Content-Type) và chọn Nhà kho (Base Directory).

        Tùy thuộc vào việc khách yêu cầu loại hàng gì (HTML, CSS, Video, Ảnh),
        hệ thống sẽ tự động chuyển hướng tìm kiếm vào đúng khu vực nhà kho tương ứng.
        """
        base_dir = ""

        if not hasattr(self, "headers") or self.headers is None:
            self.headers = {}

        if "/" not in mime_type:
            mime_type = "application/octet-stream"

        main_type, sub_type = mime_type.split("/", 1)
        print(
            "[Response] Phân loại hàng hóa: Nhóm chính={} - Nhóm phụ={}".format(
                main_type, sub_type
            )
        )

        if main_type == "text":
            self.headers["Content-Type"] = "text/{}".format(sub_type)
            if sub_type == "plain":
                base_dir = BASE_DIR + "static/"
            elif sub_type == "css":
                base_dir = BASE_DIR + "static/css/"  # Kho CSS
            elif sub_type == "html":
                base_dir = BASE_DIR + "www/"  # Kho Giao diện chính
            else:
                base_dir = BASE_DIR + "static/js/"  # Kho Logic (JS)
        elif main_type == "image":
            base_dir = BASE_DIR + "static/"
            self.headers["Content-Type"] = "image/{}".format(sub_type)
        elif main_type == "application":
            if sub_type == "javascript":
                base_dir = BASE_DIR + "static/js/"
            else:
                base_dir = BASE_DIR + "apps/"
            self.headers["Content-Type"] = "application/{}".format(sub_type)
        # --- Bắt đầu giải quyết TODO: Xử lý đa phương tiện ---
        elif main_type == "video" or main_type == "audio":
            base_dir = BASE_DIR + "static/media/"
            self.headers["Content-Type"] = f"{main_type}/{sub_type}"
        else:
            base_dir = BASE_DIR + "static/"
            self.headers["Content-Type"] = "application/octet-stream"
        # --- Kết thúc giải quyết TODO ---

        return base_dir

    def build_content(self, path, base_dir):
        """
        Quy trình "Lấy hàng từ kho" (Đọc file) kiêm "Trạm kiểm soát An ninh".

        Kỹ thuật bảo mật: Để phòng ngừa Hacker cố tình truyền vào các đường dẫn ma
        (Ví dụ: `../../../../etc/passwd`) nhằm ăn cắp thông tin nhạy cảm của máy chủ
        (Lỗ hổng Directory Traversal), hệ thống sẽ tính toán đường dẫn thực (realpath)
        để đảm bảo không có ai được phép thò tay ra khỏi nhà kho được cấp phép.
        """
        rel_path = path.lstrip("/")
        filepath = os.path.join(base_dir, rel_path)

        print("[Response] Đang lấy hàng tại kho: {}".format(filepath))

        # --- Bắt đầu giải quyết TODO: Đọc file an toàn ---
        try:
            # Thuật toán chống Directory Traversal (Chống leo thang thư mục)
            base_real = os.path.realpath(base_dir)
            target_real = os.path.realpath(filepath)

            # Nếu tọa độ cuối cùng không nằm gọn trong Nhà kho (base_real), lập tức từ chối!
            if not os.path.commonpath([base_real]) == os.path.commonpath(
                [base_real, target_real]
            ):
                raise IOError(
                    "Xâm nhập trái phép: Cố gắng truy cập ngoài thư mục an toàn"
                )

            # Đọc tệp ở chế độ Binary (Nhi phân) để giữ nguyên vẹn mọi cấu trúc hình ảnh/chữ
            with open(target_real, "rb") as f:
                content = f.read()
        except Exception as e:
            print("[Response] Lỗi quá trình lấy hàng: {}".format(e))
            return -1, b""
        # --- Kết thúc giải quyết TODO ---

        return len(content), content

    def build_response_header(self, request):
        """
        Máy in Tem Nhãn (Header Builder).
        Sản xuất đoạn văn bản tuân thủ nghiêm ngặt theo chuẩn Giao thức HTTP/1.1.
        """
        reqhdr = (
            request.headers
            if request and hasattr(request, "headers") and request.headers
            else {}
        )

        # Tem nhãn động: Ghi chú đầy đủ dung lượng, ngày tháng, và chứng chỉ bảo mật
        dynamic_headers = {
            "Accept": "{}".format(reqhdr.get("Accept", "application/json")),
            "Accept-Language": "{}".format(
                reqhdr.get("Accept-Language", "en-US,en;q=0.9")
            ),
            "Authorization": "{}".format(
                reqhdr.get("Authorization", "Basic <credentials>")
            ),
            "Cache-Control": "no-cache",
            "Content-Type": "{}".format(self.headers.get("Content-Type", "text/html")),
            "Content-Length": "{}".format(
                len(self._content) if isinstance(self._content, bytes) else 0
            ),
            "Date": "{}".format(
                datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
            ),
            "Max-Forward": "10",
            "Pragma": "no-cache",
            "Proxy-Authorization": "Basic dXNlcjpwYXNz",
            "Warning": "199 Miscellaneous warning",
            "User-Agent": "{}".format(reqhdr.get("User-Agent", "Chrome/123.0.0.0")),
            "Server": "AsynapRous-Server (Python)",
        }

        # --- Bắt đầu giải quyết TODO: Cấu trúc khuôn dạng Header ---
        status_line = f"HTTP/1.1 {self.status_code or 200} {self.reason or 'OK'}\r\n"

        header_lines = []
        for key, value in dynamic_headers.items():
            header_lines.append(f"{key}: {value}")

        # Ép các thẻ Cookie lên nhãn dán
        for key, value in self.cookies.items():
            header_lines.append(f"Set-Cookie: {key}={value}")

        # Ghép tất cả lại, dập dấu '\r\n\r\n' để báo hiệu kết thúc phần Tem Nhãn
        fmt_header = status_line + "\r\n".join(header_lines) + "\r\n\r\n"
        # --- Kết thúc giải quyết TODO ---

        return str(fmt_header).encode("utf-8")

    def build_notfound(self):
        """Khung mẫu đóng gói báo lỗi 404 Not Found (Không tìm thấy món hàng)."""
        return (
            "HTTP/1.1 404 Not Found\r\n"
            "Accept-Ranges: bytes\r\n"
            "Content-Type: text/html\r\n"
            "Content-Length: 13\r\n"
            "Cache-Control: max-age=86000\r\n"
            "Connection: close\r\n"
            "\r\n"
            "404 Not Found"
        ).encode("utf-8")

    def build_response(self, request, envelop_content=None):
        """
        Dây Chuyền Đóng Gói Cuối Cùng.
        Hàm này ra lệnh vận hành toàn bộ quy trình: Tìm kho -> Lấy hàng -> In tem -> Trả về kết quả.
        """
        print("[Response] Khởi chạy dây chuyền đóng gói cho: {}".format(request))
        path = getattr(request, "path", "/index.html")
        mime_type = self.get_mime_type(path)

        base_dir = ""

        # --- Bắt đầu giải quyết TODO: Xác định lộ trình lấy hàng ---
        if path.endswith(".html") or mime_type == "text/html":
            base_dir = self.prepare_content_type(mime_type="text/html")
        elif mime_type == "text/css":
            base_dir = self.prepare_content_type(mime_type="text/css")
        elif mime_type == "text/javascript" or mime_type == "application/javascript":
            base_dir = self.prepare_content_type(mime_type=mime_type)
        elif mime_type.startswith("image/"):
            base_dir = self.prepare_content_type(mime_type=mime_type)
        elif mime_type == "application/json" or mime_type == "application/octet-stream":
            base_dir = self.prepare_content_type(mime_type="application/json")
            envelop_content = ""
        else:
            # Mặt hàng không được siêu thị hỗ trợ
            return self.build_notfound()

        # Thực hiện móc hàng từ kho lên xe
        c_len, self._content = self.build_content(path, base_dir)
        if c_len < 0:
            return self.build_notfound()

        self.status_code = 200
        self.reason = "OK"
        # --- Kết thúc giải quyết TODO ---

        # Dán tem Header
        self._header = self.build_response_header(request)

        # Hợp nhất: Trả về [Tem Nhãn] + [Hàng Hóa]
        return self._header + self._content

    # ==============================================================================
    # CÁC KỊCH BẢN ĐÓNG GÓI ĐẶC BIỆT DÀNH CHO API CỦA WEB CHAT P2P
    # ==============================================================================

    def build_unauthorized(self):
        """Đuổi khách: Báo lỗi 401 Unauthorized khi phát hiện chưa mua vé (Đăng nhập)."""
        self.status_code = 401
        self.reason = "Unauthorized"
        content = b"401 Unauthorized"

        headers = (
            f"HTTP/1.1 {self.status_code} {self.reason}\r\n"
            "Content-Type: text/plain\r\n"
            f"Content-Length: {len(content)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        return headers.encode("utf-8") + content

    def build_login_success(self, request):
        """Đóng dấu Thẻ VIP (Cookie auth=true) và dắt khách về sảnh chính (index.html)."""
        self.cookies["auth"] = "true; Path=/"
        request.path = "/index.html"
        request.method = "GET"
        return self.build_response(request)

    def build_success(self, body):
        """Phục vụ bữa tiệc 200 OK với cấu trúc dữ liệu JSON thuần túy."""
        json_body = json.dumps(body)
        content_length = len(json_body.encode("utf-8"))
        return (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {content_length}\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{json_body}"
        ).encode("utf-8")

    def build_bad_request(self, body):
        """Từ chối phục vụ (400 Bad Request) do khách hàng điền sai mẫu đơn."""
        json_body = json.dumps(body)
        content_length = len(json_body.encode("utf-8"))
        return (
            "HTTP/1.1 400 Bad Request\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {content_length}\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{json_body}"
        ).encode("utf-8")

    def build_internal_error(self, body):
        """Báo động đỏ (500 Internal Error) do nhà bếp tự cháy, không liên quan khách hàng."""
        json_body = json.dumps(body)
        content_length = len(json_body.encode("utf-8"))
        return (
            "HTTP/1.1 500 Internal Server Error\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {content_length}\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{json_body}"
        ).encode("utf-8")
