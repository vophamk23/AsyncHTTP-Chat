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
daemon.asynaprous
~~~~~~~~~~~~~~~~~

Module này cung cấp lớp `AsynapRous` - đóng vai trò là "bộ não" điều phối 
toàn bộ ứng dụng Web. Nó chịu trách nhiệm định tuyến (routing) các yêu cầu (Request)
từ trình duyệt đến đúng hàm xử lý tương ứng thông qua cơ chế RESTful API.
"""

from .backend import create_backend
import asyncio
import inspect

class AsynapRous:
    """
    Lớp :class:`AsynapRous <AsynapRous>` là một Web Framework tự xây dựng, 
    nhỏ gọn nhưng mạnh mẽ, hoạt động tương tự như Flask hay FastAPI.

    Nhiệm vụ chính của nó là cung cấp một bộ định tuyến (Router). Khi bạn lập trình, 
    bạn chỉ cần gắn nhãn `@app.route()` lên đầu một hàm, AsynapRous sẽ tự động 
    hiểu rằng: "Khi có người truy cập vào đường link này, hãy chạy hàm này".

    Sau khi cấu hình xong, Framework sẽ khởi động một máy chủ TCP (Backend Server) 
    để túc trực và lắng nghe các kết nối từ người dùng.

    Ví dụ cách sử dụng (Usage)::

      >>> import daemon.asynaprous
      >>> app = daemon.asynaprous.AsynapRous()
      
      >>> @app.route('/login', methods=['POST'])
      >>> def login_handler(req):
      >>>     return Response().build_success({'msg': 'Đăng nhập thành công'})

      >>> app.prepare_address('127.0.0.1', 9000)
      >>> app.run()
    """

    def __init__(self):
        """
        Khởi tạo hệ thống AsynapRous.
        
        Thiết lập một "Bản đồ định tuyến" (Routes) rỗng. Bản đồ này sẽ dần 
        được lấp đầy khi lập trình viên sử dụng decorator `@app.route`.
        """
        #: Bản đồ định tuyến: Lưu trữ dạng từ điển {('METHOD', '/đường_dẫn'): hàm_xử_lý}
        self.routes = {}
        #: Địa chỉ IP của máy chủ
        self.ip = None
        #: Cổng mạng mà máy chủ sẽ sử dụng
        self.port = None
        return

    def prepare_address(self, ip, port):
        """
        Khai báo địa chỉ IP và Cổng mạng (Port) cho máy chủ.
        Lưu ý: Bắt buộc phải chạy hàm này trước khi gọi `app.run()`.

        :param ip (str): Địa chỉ IP (Ví dụ: '127.0.0.1' cho Localhost).
        :param port (int): Cổng mạng (Ví dụ: 9000).
        """
        self.ip = ip
        self.port = port

    def route(self, path, methods=['GET']):
        """
        Hàm trang trí (Decorator) dùng để đăng ký một API endpoint.

        Khi bạn viết `@app.route('/path')` phía trên một hàm, AsynapRous sẽ tự động 
        ghi nhớ hàm đó vào "Bản đồ định tuyến". Bất cứ khi nào có yêu cầu (Request) 
        gửi tới '/path', AsynapRous sẽ tra bản đồ và lôi hàm này ra để thực thi.

        Hàm hỗ trợ cả lập trình Đồng bộ (Sync) lẫn Bất đồng bộ (Async/Coroutine).

        :param path (str): Đường dẫn trên URL (Ví dụ: '/api/chat').
        :param methods (list): Các phương thức HTTP cho phép (Ví dụ: ['GET', 'POST']).

        :kiểu trả về (rtype): Một hàm bọc (wrapper) đã được đăng ký hệ thống.
        """
        def decorator(func):
            # Cập nhật bản đồ định tuyến cho từng phương thức (GET, POST...)
            for method in methods:
                self.routes[(method.upper(), path)] = func

            # Gắn thêm nhãn thông tin để phục vụ gỡ lỗi (debug) nếu cần
            func._route_path = path
            func._route_methods = methods

            # ---------------------------------------------------------
            # Khối bọc bảo vệ (Wrapper) dành cho các hàm Đồng bộ (Sync)
            # ---------------------------------------------------------
            def sync_wrapper(*args, **kwargs):
               print("[AsynapRous] Thực thi luồng Đồng Bộ (Sync) -> [{}] {}".format(methods, path))
               result = func(*args, **kwargs)
               return result

            # ---------------------------------------------------------
            # Khối bọc bảo vệ (Wrapper) dành cho hàm Bất đồng bộ (Async)
            # ---------------------------------------------------------
            async def async_wrapper(*args, **kwargs):
               print("[AsynapRous] Thực thi luồng Bất Đồng Bộ (Async) -> [{}] {}".format(methods, path))
               result = await func(*args, **kwargs)
               return result

            # Tự động nhận diện kiểu hàm mà lập trình viên đã viết 
            # để trả về lớp bọc (wrapper) tương ứng một cách thông minh
            if inspect.iscoroutinefunction(func):
               return async_wrapper
            else:
               return sync_wrapper
               
        return decorator

    def run(self):
        """
        Kích hoạt toàn bộ hệ thống máy chủ (Backend Server).

        Hàm này sẽ đánh thức hệ thống mạng TCP (thông qua `create_backend`), 
        bàn giao lại địa chỉ IP, Cổng mạng và "Bản đồ định tuyến" (Routes) 
        để máy chủ bắt đầu mở cửa đón khách.
        """
        # Kiểm tra an toàn: Đảm bảo IP và Port đã được khai báo
        if not self.ip or not self.port:
            print("[AsynapRous] LỖI: Vui lòng cấu hình mạng trước "
                  "bằng cách gọi lệnh app.prepare_address(ip, port)")
            return

        # Bàn giao dữ liệu và khởi động động cơ mạng lõi
        create_backend(self.ip, self.port, self.routes)
