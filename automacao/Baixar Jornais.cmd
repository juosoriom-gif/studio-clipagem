@echo off
chcp 65001 >nul
title Clipagem - Download de Jornais
cd /d "%~dp0"

echo ============================================
echo   CLIPAGEM - DOWNLOAD DE JORNAIS
echo ============================================
echo.

py "scripts\baixar_jornal.py" agazeta
if errorlevel 1 (
  echo.
  echo [!] A Gazeta falhou. Veja o log em automacao\logs\.
) else (
  echo.
  echo [OK] A Gazeta concluida.
)

echo.
echo ============================================
echo Arquivos em: JORNAIS\^<jornal^>\^<edicao^>\
echo ============================================
echo.
pause
