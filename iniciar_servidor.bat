@echo off
title PollaF - Servidor Django
cd /d "%~dp0"
echo.
echo  =========================================
echo   PollaF 2026 - Servidor de desarrollo
echo  =========================================
echo.
echo  Abre tu navegador en:
echo  http://127.0.0.1:8000
echo.
echo  Presiona Ctrl+C para detener el servidor.
echo.
python manage.py runserver
pause
