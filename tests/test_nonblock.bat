@echo off
title Stress Test: Non-blocking Verification
cls

echo ==============================================================================
echo [HE THONG KIEM TRA TINH NANG NON-BLOCKING - ASYNAPROUS]
echo ==============================================================================
echo.
echo [1. CACH CHAY]:
echo    - Buoc 1: Chay file 'run_web.bat' de khoi dong Server.
echo    - Buoc 2: Chon che do (Threading/Callback/Coroutine) trong Server.
echo    - Buoc 3: Chay file nay de gia lap 100 nguoi dung truy cap cung luc.
echo.
echo [2. GIAI THICH CO CHE TEST]:
echo    - BLOCKING: Server xu ly tung nguoi mot (xong nguoi 1 moi den nguoi 2).
echo      => Tong thoi gian = 100 x (thoi gian 1 request). Rat cham!
echo    - NON-BLOCKING: Server tiep nhan va xu ly 100 nguoi cung mot luc.
echo      => Tong thoi gian gan bang thoi gian cua 1 request duy nhat. Rat nhanh!
echo.
echo [3. KY VONG]: 
echo    - Ket qua phai thay 100 dong "Nhan phan hoi" chay ra lien tuc.
echo    - TOTAL TIME phai < 2 giay (neu chay tren localhost).
echo.
echo ------------------------------------------------------------------------------
echo Nhan phim bat ky de bat dau Stress Test...
pause > nul
echo.

if exist "test_nonblock.py" (
    python test_nonblock.py
) else (
    python tests/test_nonblock.py
)

echo.
echo ------------------------------------------------------------------------------
echo [KET LUAN]: 
echo  - Neu TOTAL TIME thap: Server cua ban da dat tieu chuan Non-blocking.
echo  - Neu TOTAL TIME cao: Hay kiem tra xem ban co dang de Server o che do
echo    don luong (Blocking) hay khong.
echo ------------------------------------------------------------------------------
pause
