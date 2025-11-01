@echo off
setlocal

if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\activate
pip install --upgrade pip
pip install PySide6
pip install openai

REM Ask for OpenAI API token
set /p OPENAI_API_KEY=Enter your OpenAI API token: 
setx OPENAI_API_KEY "%OPENAI_API_KEY%"

REM Set default cat size if not specified
if not defined CAT_SIZE set CAT_SIZE=160

python -m mycat.main

if errorlevel 1 (
  echo.
  echo [!] The app exited with an error. See messages above.
)
echo.
pause
