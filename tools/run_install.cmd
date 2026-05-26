@echo off
cd /d "%~dp0.."
python "%~dp0install_agentic_dev_skills.py" --setup
if errorlevel 1 python "%~dp0install_agentic_dev_skills.py" --copy --setup
pause
