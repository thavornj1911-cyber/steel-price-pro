@echo off
chcp 65001 >nul
title ดึงราคาเหล็ก 2S Metal ล่าสุด (เรียลไทม์)
cd /d "%~dp0"
python sync_2s_live.py
