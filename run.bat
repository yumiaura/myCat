@echo off
REM Launch mycat on Windows. Passes through any flags, e.g.:
REM   run.bat              default
REM   run.bat --openai     OpenAI chat
REM   run.bat --ollama     Ollama chat
setlocal
cd /d "%~dp0"
python -m mycat %*
