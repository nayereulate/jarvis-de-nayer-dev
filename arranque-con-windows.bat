@echo off
rem Doble clic: Jarvis arranca solo (minimizado) cada vez que inicias sesión en Windows.
rem Para quitarlo: arranque-con-windows.bat quitar
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.lnk"
if /i "%~1"=="quitar" (
  if exist "%LINK%" del "%LINK%"
  echo Jarvis ya no arranca con Windows.
  pause
  exit /b
)
powershell -NoProfile -Command "$s = New-Object -ComObject WScript.Shell; $l = $s.CreateShortcut($env:LINK); $l.TargetPath = '%~dp0iniciar.bat'; $l.Arguments = 'auto'; $l.WorkingDirectory = '%~dp0'; $l.WindowStyle = 7; $l.Description = 'Jarvis'; $l.Save()"
if exist "%LINK%" (echo Listo: Jarvis arrancara solo al iniciar Windows.) else (echo No pude crear el acceso directo.)
pause
