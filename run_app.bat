@echo off
chcp 65001 > nul
title 2S Metal Steel Pricing & Margin Pro
echo ========================================================
echo   2S Metal Steel Cost & Margin Pro
echo   ระบบเทียบต้นทุนเหล็ก 2S Metal & คำนวณกำไร-ส่วนลด
echo ========================================================
echo.
cd /d "%~dp0"

echo [1/2] กำลังตรวจสอบความพร้อมของระบบ...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] ไม่พบ Python ในระบบ กรุณาติดตั้ง Python ก่อน
    pause
    exit /b 1
)

echo [2/2] เริ่มต้นเซิร์ฟเวอร์ที่ http://localhost:8099 ...
start "" http://localhost:8099
python server.py

pause
