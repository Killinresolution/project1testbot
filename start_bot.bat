@echo off
echo Останавливаю предыдущие экземпляры бота...
for /f "tokens=1" %%i in ('wmic process where "name='python.exe' and CommandLine like '%%bot.py%%'" get ProcessId ^| findstr /r "[0-9]"') do (
    taskkill /PID %%i /F >nul 2>&1
)
timeout /t 3 /nobreak >nul
echo Запускаю EzraTest1Bot...
cd /d "%~dp0"
python bot.py
