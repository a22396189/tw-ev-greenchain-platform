@echo off
chcp 65001 >nul
echo This removes all containers AND the database volume (back to a clean state). Continue?
pause
docker compose down -v
echo Reset done. The next start_demo.bat will rebuild tables and re-run the backfill.
pause
