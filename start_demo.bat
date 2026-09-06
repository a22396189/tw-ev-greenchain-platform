@echo off
chcp 65001 >nul
echo ============================================
echo   TW EV ^& Green-Energy Supply-Chain Platform - starting
echo ============================================
echo.

echo [1/5] Building crawler / api images (slow on first run)...
docker compose build
if errorlevel 1 goto :error

echo.
echo [2/5] Starting MySQL and waiting for it to be ready...
docker compose up -d mysql
set HSTATUS=
:wait_mysql
for /f %%i in ('docker inspect -f "{{.State.Health.Status}}" tw-greenchain-platform-mysql-1 2^>nul') do set HSTATUS=%%i
if not "%HSTATUS%"=="healthy" (
    timeout /t 3 >nul
    goto :wait_mysql
)
echo       MySQL is ready.

echo.
echo [3/5] Creating tables, loading seed data, backfilling history (needs internet, a few minutes)...
docker compose run --rm crawler python -m greenchain.seed
if errorlevel 1 (
    echo       [warn] init reported an error, but it may just be a partial backfill failure; continuing.
)

echo.
echo [4/5] Starting the rest of the stack (API / Airflow / Prometheus / Grafana / phpMyAdmin)...
docker compose up -d
if errorlevel 1 goto :error

echo.
echo [5/5] Waiting for services to come up (Airflow is slowest, ~1-2 min)...
timeout /t 20 >nul

echo.
echo ============================================
echo   All up. Opening browser tabs...
echo ============================================
start http://localhost:3000
start http://localhost:8080
start http://localhost:8888/docs
start http://localhost:9090

echo.
echo   Grafana      : http://localhost:3000   (admin / admin)
echo   Airflow      : http://localhost:8080   (admin / admin)
echo   API docs     : http://localhost:8888/docs
echo   Prometheus   : http://localhost:9090
echo   phpMyAdmin   : http://localhost:8000   (root / see MYSQL_ROOT_PASSWORD in .env)
echo.
echo   If Grafana or Airflow still spins on open, wait 30-60s and refresh.
pause
exit /b 0

:error
echo.
echo   [error] Something failed during startup; screenshot the messages above.
pause
exit /b 1
