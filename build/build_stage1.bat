@echo off
rem ============================================================
rem  AirType Stage1 compile (C# 5, system csc.exe)
rem  Usage: run from anywhere: build\build_stage1.bat
rem  NOTE: keep this file ASCII-only (cmd parses bat as ANSI/GBK)
rem ============================================================
setlocal
cd /d "%~dp0.."

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
  echo [ERROR] csc.exe not found. .NET Framework 4.x required.
  exit /b 1
)

if not exist build mkdir build

rem NOTE: src\AirType.cs must be UTF-8 WITH BOM (csc reads BOM-less
rem       UTF-8 as ANSI/GBK and corrupts Chinese string literals)

rem AnyCPU：同一 exe 同时跑 32 位/64 位系统（Win7 有 32 位老机器），
rem 代码 P/Invoke 已用 IntPtr 自适应位数。
"%CSC%" /nologo /optimize+ /platform:anycpu /target:winexe ^
  /r:System.dll /r:System.Core.dll /r:System.Drawing.dll ^
  /r:System.Windows.Forms.dll /r:System.Web.Extensions.dll ^
  /res:src\web\index.html,AirTypeRes.index.html ^
  /res:src\web\pair.html,AirTypeRes.pair.html ^
  /res:src\web\mobile.html,AirTypeRes.mobile.html ^
  /res:src\web\qrcode.js,AirTypeRes.qrcode.js ^
  /out:build\AirType.exe src\AirType.cs
if errorlevel 1 (
  echo [ERROR] compile failed.
  exit /b 1
)

echo [OK] build\AirType.exe built.
echo.
echo Next steps:
echo   1. run build\AirType.exe    (double-click works too)
echo      The app is a tray app - no console window, no arguments needed.
echo   2. the pairing page opens in your browser automatically
echo   3. scan the QR code with your phone, then type on the phone
echo   4. tray icon (bottom-right) right-click menu:
echo      show QR code / new pairing code / pause / autostart / log / quit
endlocal
