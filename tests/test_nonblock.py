import socket
import threading
import time

# Cấu hình IP và Port của Backend hoặc Proxy (ví dụ Backend đang chạy ở 9000)
TARGET_IP = "127.0.0.1"
TARGET_PORT = 9000 
NUM_CLIENTS = 100 # Số lượng request đồng thời

def simulate_client(client_id):
    try:
        # Khởi tạo kết nối TCP
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((TARGET_IP, TARGET_PORT))
        
        # Gửi một HTTP Request cơ bản
        request = f"GET /login HTTP/1.1\r\nHost: {TARGET_IP}\r\nConnection: close\r\n\r\n"
        s.sendall(request.encode('utf-8'))
        
        # Chờ và nhận phản hồi
        response = s.recv(1024).decode('utf-8')
        status_line = response.splitlines()[0] if response else "No Response"
        
        print(f"[Client {client_id:03d}] Nhận phản hồi: {status_line}")
        s.close()
    except Exception as e:
        print(f"[Client {client_id:03d}] LỖI: {e}")

if __name__ == "__main__":
    print(f"--- BẮT ĐẦU TEST NON-BLOCKING VỚI {NUM_CLIENTS} CLIENTS ---")
    start_time = time.time()
    
    threads = []
    # Sinh ra hàng loạt luồng (Mô phỏng hàng loạt khách truy cập cùng lúc)
    for i in range(NUM_CLIENTS):
        t = threading.Thread(target=simulate_client, args=(i,))
        threads.append(t)
        t.start()
        
    # Chờ tất cả các client hoàn thành
    for t in threads:
        t.join()
        
    end_time = time.time()
    print(f"--- HOÀN THÀNH TRONG {end_time - start_time:.2f} GIÂY ---")
