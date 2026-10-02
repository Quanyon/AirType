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

rem Release the output exe if a previous instance is still running in the tray,
rem otherwise csc cannot overwrite build\AirType.exe (file locked).
taskkill /f /im AirType.exe >nul 2>&1

rem NOTE: src\AirType.cs must be UTF-8 WITH BOM (csc reads BOM-less
rem       UTF-8 as ANSI/GBK and corrupts Chinese string literals)

rem AnyCPU: one exe runs on both 32-bit and 64-bit systems (legacy Win7).
rem P/Invoke signatures use IntPtr so they adapt to the process bitness.
"%CSC%" /nologo /optimize+ /platform:anycpu /target:winexe ^
  /win32icon:src\airtype.ico ^
  /r:System.dll /r:System.Core.dll /r:System.Drawing.dll ^
  /r:System.Windows.Forms.dll /r:System.Web.Extensions.dll ^
  /res:src\web\index.html,AirTypeRes.index.html ^
  /res:src\web\pair.html,AirTypeRes.pair.html ^
  /res:src\web\mobile.html,AirTypeRes.mobile.html ^
  /res:src\web\qrcode.js,AirTypeRes.qrcode.js ^
  /res:src\airtype.ico,AirTypeRes.airtype.ico ^
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
