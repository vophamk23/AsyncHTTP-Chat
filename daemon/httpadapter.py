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
"""

from .request import Request
from .response import Response
from .dictionary import CaseInsensitiveDict

import asyncio
import inspect
import json


class HttpAdapter:
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
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes
        self.request = Request()
        self.response = Response()

    def handle_client(self, conn, addr, routes):
        self.conn = conn        
        self.connaddr = addr
        req = self.request
        resp = self.response

        # 1. ĐỌC HEADER
        conn.settimeout(2)  
        raw = b""
        try:
            while b"\r\n\r\n" not in raw:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
        except Exception:
            pass

        if not raw:
            try: conn.close()
            except Exception: pass
            return

        header_end = raw.find(b"\r\n\r\n")
        header_bytes = raw[: header_end + 4] if header_end != -1 else raw
        header_text = header_bytes.decode("utf-8", errors="replace")

        req.prepare(header_text, routes)
        print("[HttpAdapter] Đang xử lý giao dịch ĐỒNG BỘ từ {}".format(addr))

        # 2. ĐỌC BODY
        content_length = int(req.headers.get("content-length", 0))
        body = raw[header_end + 4 :] if header_end != -1 else b""
        to_read = content_length - len(body)
        
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
            try: conn.sendall(data_bytes)
            except Exception: pass
            try: conn.close()
            except Exception: pass

        # 3. TRẠM KIỂM SOÁT AN NINH
        public_pages = ["/login.html"]
        
        if req.method == "GET" and req.path.endswith(".html") and req.path not in public_pages:
            cookie_val = req.cookies.get("auth", "")
            is_auth = (cookie_val and cookie_val.split(";", 1)[0].strip() == "true")
            
            if not is_auth:
                send_and_close(resp.build_unauthorized())
                return
            
            send_and_close(resp.build_response(req))
            return

        # 4. ĐIỀU PHỐI LOGIC
        if req.hook:
            try:
                api_response = req.hook(req)
                send_and_close(api_response)
                return
            except Exception as e:
                err = json.dumps({"error": "Lỗi máy chủ nội bộ", "message": str(e)})
                response_bytes = (
                    "HTTP/1.1 500 Internal Server Error\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(err.encode('utf-8'))}\r\n"
                    "Connection: close\r\n\r\n" f"{err}"
                ).encode("utf-8")
                send_and_close(response_bytes)
                return

        send_and_close(resp.build_response(req))
        return

    async def handle_client_coroutine(self, reader, writer):
        req = self.request
        resp = self.response
        addr = writer.get_extra_info("peername")

        print("[HttpAdapter] Đang xử lý giao dịch BẤT ĐỒNG BỘ từ {}".format(addr))

        raw = b""

        # 1. ĐỌC HEADER
        try:
            while b"\r\n\r\n" not in raw:
                chunk = await reader.read(1024)
                if not chunk:
                    break
                raw += chunk
        except Exception:
            writer.close()
            return

        if not raw:
            writer.close()
            return

        header_end = raw.find(b"\r\n\r\n")
        header_bytes = raw[:header_end + 4]
        header_text = header_bytes.decode("utf-8", errors="replace")

        req.prepare(header_text, routes=self.routes)

        # 2. ĐỌC BODY 
        content_length = int(req.headers.get("content-length", 0))
        body = raw[header_end + 4:]

        to_read = content_length - len(body)

        try:
            while to_read > 0:
                chunk = await reader.read(min(1024, to_read))
                if not chunk:
                    break
                body += chunk
                to_read -= len(chunk)
        except Exception:
            pass

        req.body = body.decode("utf-8", errors="replace")

        # 3. AUTH CHECK 
        public_pages = ["/login.html"]

        if req.method == "GET" and req.path.endswith(".html") and req.path not in public_pages:
            cookie_val = req.cookies.get("auth", "")
            is_auth = (cookie_val and cookie_val.split(";", 1)[0].strip() == "true")
            
            if not is_auth:
                writer.write(resp.build_unauthorized())
                await writer.drain()
                writer.close()
                return

        # 4. ROUTING VÀ TRẢ FILE
        if req.hook:
            try:
                if inspect.iscoroutinefunction(req.hook):
                    response = await req.hook(req)
                else:
                    response = req.hook(req)
            except Exception as e:
                err = json.dumps({"error": str(e)})
                response = (
                    "HTTP/1.1 500 Internal Server Error\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(err.encode())}\r\n\r\n"
                    f"{err}"
                ).encode()
        else:
            try:
                response = resp.build_response(req)
            except Exception as e:
                print(f"[Error] Không thể tải file tĩnh: {e}")
                response = b"HTTP/1.1 500 Internal Error\r\n\r\n"

        # 5. SEND RESPONSE
        writer.write(response)
        await writer.drain()
        writer.close()