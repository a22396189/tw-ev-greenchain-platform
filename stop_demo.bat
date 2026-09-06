@echo off
chcp 65001 >nul
echo Stopping all containers (database contents are kept; next start skips the backfill)...
docker compose down
echo.
echo Done. To wipe data and start clean, use reset_demo.bat instead.
pause
