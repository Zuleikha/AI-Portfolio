@echo off
echo Starting Pharma-AI environment...
echo.

REM Activate the conda environment called "pharma-ai-env"
call conda activate pharma-ai-env

REM Move to the project folder (where this .bat file lives)
cd /d "%~dp0"

echo Environment activated. You are now in:
echo   %CD%
echo.

REM Keep the window open for the user
cmd
