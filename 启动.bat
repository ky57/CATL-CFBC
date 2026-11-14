@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0"
set "PYTHONUTF8=1"
python app.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
if not "%EXITCODE%"=="0" (
  echo.
  echo 服务启动失败，请把上面的错误信息发给维护人。
  pause
)
endlocal
