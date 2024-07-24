@echo off
:: Check for administrative privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    :: If running as administrator, run the taskkill command
    taskkill /F /IM osk.exe >nul 2>&1
) else (
    :: If not running as administrator, prompt for elevation
    echo Requesting administrative privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c taskkill /F /IM osk.exe' -Verb RunAs -WindowStyle Hidden"
)
