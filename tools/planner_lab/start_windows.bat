@echo off
setlocal
cd /d "%~dp0..\.."
echo.
echo Energy Co-Pilot Planner Lab - lokalny serwer bez Home Assistant
echo Otworz w przegladarce: http://127.0.0.1:8765
echo Zamkniecie: Ctrl+C
echo.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 tools\planner_lab\server.py
) else (
    python tools\planner_lab\server.py
)
if errorlevel 1 (
    echo Nie udalo sie uruchomic laboratorium. Sprawdz instalacje Python 3.11+.
    pause
)
