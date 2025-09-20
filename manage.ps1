<#
  Менеджер разработки COLIZEUM (PowerShell)

  Возможности:
    1. Запуск сервера (в фоне, логи в logs/*.log)
    2. Перезапуск сервера
    3. Остановка сервера
    4. Статус сервера
    5. Просмотр логов

  Использование:
    powershell -ExecutionPolicy Bypass -File .\manage.ps1
    .\manage.ps1 -Action start|stop|restart|status|tail|menu
#>

[CmdletBinding()]
param(
  [ValidateSet('start','stop','restart','status','tail','dbinit','dbmigrate','dbupgrade','dbstamp','dbcurrent','menu')]
  [string]$Action = 'menu',
  [string]$Message = 'auto',
  [string]$Revision = 'head',
  [ValidateSet('ask','yes','no')]
  [string]$MigrateOnStart = 'ask',
  [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
# Корректный вывод UTF-8 в консоль
try {
  $enc = [System.Text.UTF8Encoding]::new($false)
  [Console]::OutputEncoding = $enc
  $OutputEncoding = $enc
} catch {}

$Root   = Split-Path -Parent $PSCommandPath
$Venv   = Join-Path $Root '.venv'
$Py     = Join-Path $Venv 'Scripts\python.exe'
$Flask  = Join-Path $Venv 'Scripts\flask.exe'
$LogDir = Join-Path $Root 'logs'
$PidFile= Join-Path $LogDir 'server.pid'

function Write-Info($m){ Write-Host "[ИНФО] $m" -ForegroundColor Cyan }
function Write-Warn($m){ Write-Host "[ВНИМАНИЕ] $m" -ForegroundColor Yellow }
function Write-Err ($m){ Write-Host "[ОШИБКА] $m" -ForegroundColor Red }

function Ensure-Dir($p){ if(-not (Test-Path $p)){ New-Item -ItemType Directory -Path $p | Out-Null } }

function Ensure-VenvAndDeps {
  if(-not (Test-Path $Py)){
    Write-Info "Создаю виртуальную среду (.venv)..."
    if(Get-Command py -ErrorAction SilentlyContinue){ py -3 -m venv $Venv }
    else { python -m venv $Venv }
  }
  if(-not (Test-Path $Flask)){
    Write-Info "Устанавливаю зависимости..."
    & $Py -m pip install -U pip
    & $Py -m pip install -r (Join-Path $Root 'requirements.txt')
  } else {
    Write-Info "Зависимости уже установлены."
  }
}

function Ensure-Database {
  $dbPath = Join-Path (Join-Path $Root 'instance') 'colizeum.db'
  if(-not (Test-Path $dbPath)){
    Write-Info "Инициализирую базу данных (первый запуск)..."
    $env:PYTHONPATH = $Root
    & $Py (Join-Path $Root 'scripts\recreate_db.py')
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  }
}

function Ensure-FlaskAppEnv {
  if(-not $env:FLASK_APP){ $env:FLASK_APP = 'app:create_app' }
  if(-not $env:PYTHONPATH){ $env:PYTHONPATH = $Root }
}

# Возвращает информацию о ревизиях Alembic (head и текущая в БД)
function Get-DbRevisions {
  Ensure-FlaskAppEnv
  $headsOut = ''
  $currOut  = ''
  try { $headsOut = (& $Flask db heads 2>$null | Out-String) } catch { $headsOut = '' }
  try { $currOut  = (& $Flask db current 2>$null | Out-String) } catch { $currOut  = '' }
  if([string]::IsNullOrWhiteSpace($headsOut)){
    $prev=$ErrorActionPreference; $ErrorActionPreference='Continue'
    try { $headsOut = (& $Flask db heads 2>&1 | Out-String) } catch {}
    $ErrorActionPreference=$prev
  }
  if([string]::IsNullOrWhiteSpace($currOut)){
    $prev=$ErrorActionPreference; $ErrorActionPreference='Continue'
    try { $currOut = (& $Flask db current 2>&1 | Out-String) } catch {}
    $ErrorActionPreference=$prev
  }
  $rx = [regex]'[0-9a-f]{6,}'
  $heads = @(); foreach($m in $rx.Matches($headsOut)){ $heads += $m.Value }
  $heads = $heads | Select-Object -Unique
  $curr  = @(); foreach($m in $rx.Matches($currOut)){ $curr  += $m.Value }
  $curr  = $curr  | Select-Object -Unique
  return [pscustomobject]@{ Heads=$heads; Current=$curr; RawHeads=$headsOut.Trim(); RawCurrent=$currOut.Trim() }
}

function DB-Init { Ensure-VenvAndDeps; Ensure-FlaskAppEnv; & $Flask db init }
function DB-Migrate { Ensure-VenvAndDeps; Ensure-FlaskAppEnv; & $Flask db migrate -m $Message }
function DB-Upgrade { Ensure-VenvAndDeps; Ensure-FlaskAppEnv; & $Flask db upgrade }
function DB-Stamp { Ensure-VenvAndDeps; Ensure-FlaskAppEnv; & $Flask db stamp $Revision }
function DB-Current { Ensure-VenvAndDeps; Ensure-FlaskAppEnv; & $Flask db current }

function Get-ServerPID {
  if(Test-Path $PidFile){
    try{ $savedId = [int](Get-Content $PidFile | Select-Object -First 1) } catch { return $null }
    $p = Get-Process -Id $savedId -ErrorAction SilentlyContinue
    if($p){ return $p.Id } else { return $null }
  }
  return $null
}

function Start-Server {
  $running = Get-ServerPID
  if($running){ Write-Warn "Сервер уже запущен (PID=$running)."; return }
  Ensure-Dir $LogDir
  Ensure-VenvAndDeps
  Ensure-Database
  Ensure-FlaskAppEnv

  # Проверка актуальности схемы БД
  $rev = Get-DbRevisions
  $ok = $false
  if(($rev.Heads.Count -eq 0) -and ($rev.Current.Count -eq 0)) { $ok = $true } else {
    if($rev.Heads.Count -gt 0){
      $missing = @($rev.Heads | Where-Object { $rev.Current -notcontains $_ })
      $ok = ($missing.Count -eq 0)
    } else {
      $ok = $true
    }
  }

  if(-not $ok){
    Write-Warn 'База данных не на последней версии.'
    if($NonInteractive -or $MigrateOnStart -eq 'yes'){
      $resp = 'Y'
    } elseif($MigrateOnStart -eq 'no'){
      $resp = 'N'
    } else {
      $resp = Read-Host 'Обнаружены изменения схемы БД. Применить сейчас? [Y/N] (Y по умолчанию)'
    }
    if([string]::IsNullOrWhiteSpace($resp) -or $resp -match '^(y|Y|д|Д)$'){
      try {
        & $Flask db upgrade
      } catch {
        Write-Err 'Не удалось применить миграции автоматически.'
        Write-Host 'Что сделать вручную:' -ForegroundColor Yellow
        Write-Host '  1) В главном меню выберите: 7) Применить миграции (upgrade)' -ForegroundColor Yellow
        Write-Host '  2) Если база уже совпадает по структуре, но без метки — 9) Проставить head (stamp)' -ForegroundColor Yellow
        return
      }
      # Проверим ещё раз после upgrade
      $rev = Get-DbRevisions
      $missing = @($rev.Heads | Where-Object { $rev.Current -notcontains $_ })
      if($missing.Count -gt 0){
        Write-Err 'После применения миграций база всё ещё не на head.'
        Write-Host ('Текущая метка: ' + ($rev.RawCurrent))
        Write-Host ('Ожидаемая head: ' + ($rev.RawHeads))
        return
      }
      Write-Info 'Миграции успешно применены.'
    } else {
      Write-Host 'Ок, миграции не применяю. Подсказка:' -ForegroundColor Yellow
      Write-Host '  1) В меню выберите 7) Применить миграции (upgrade)' -ForegroundColor Yellow
      Write-Host '  2) Затем снова 1) Запустить сервер' -ForegroundColor Yellow
      return
    }
  }
  else {
    if($rev.Heads.Count -gt 0){
      $curStr = if($rev.Current.Count -gt 0) { ($rev.Current -join ', ') } else { ($rev.Heads -join ', ') }
      Write-Info ('База данных актуальна (rev: ' + $curStr + ')')
    } else {
      Write-Info 'Миграции отсутствуют — проверка не требуется.'
    }
  }

  $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
  $log = Join-Path $LogDir ("server-$ts.log")
  $elog = Join-Path $LogDir ("server-$ts.err.log")
  Write-Info "Запускаю сервер, лог: $log (ошибки: $elog)"
  $p = Start-Process -FilePath $Py -ArgumentList 'run.py' -WorkingDirectory $Root -RedirectStandardOutput $log -RedirectStandardError $elog -PassThru -WindowStyle Hidden
  $p.Id | Out-File -FilePath $PidFile -Encoding ascii -Force
  Start-Sleep -Milliseconds 300
  if(Get-Process -Id $p.Id -ErrorAction SilentlyContinue){ Write-Info "Сервер запущен (PID=$($p.Id))." }
  else { Write-Err "Не удалось запустить сервер. Смотрите лог: $log" }
}

function Stop-Server {
  $srvPid = Get-ServerPID
  if(-not $srvPid){ Write-Warn 'Сервер не запущен.'; return }
  Write-Info "Останавливаю сервер (PID=$srvPid)..."
  try { Stop-Process -Id $srvPid -Force -ErrorAction Stop } catch {}
  Remove-Item $PidFile -ErrorAction SilentlyContinue
  Write-Info 'Сервер остановлен.'
}

function Restart-Server { Stop-Server; Start-Server }

function Status-Server {
  $srvPid = Get-ServerPID
  if($srvPid){ Write-Info "Сервер ЗАПУЩЕН (PID=$srvPid)." } else { Write-Warn 'Сервер НЕ запущен.' }
  if(Test-Path $LogDir){
    $last = Get-ChildItem $LogDir -Filter 'server-*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if($last){ Write-Host ("Последний лог: " + $last.FullName) }
  }
}

function Tail-Logs {
  Ensure-Dir $LogDir
  $last = Get-ChildItem $LogDir -Filter 'server-*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if(-not $last){ Write-Warn 'Логов пока нет.'; return }
  Write-Info ('Просмотр лога - Ctrl+C для выхода: ' + $last.FullName)
  Get-Content -Path $last.FullName -Wait -Tail 200
}

function Show-Menu {
  while($true){
    Write-Host ''
    Write-Host '=== Менеджер разработки COLIZEUM ===' -ForegroundColor Green
    Write-Host '1) Запустить сервер'
    Write-Host '2) Перезапустить сервер'
    Write-Host '3) Остановить сервер'
    Write-Host '4) Статус'
    Write-Host '5) Смотреть логи'
    Write-Host '--- База данных ---'
    Write-Host '6) Миграция: autogenerate'
    Write-Host '7) Применить миграции (upgrade)'
    Write-Host '8) Текущая ревизия'
    Write-Host '9) Проставить head (stamp)'
    Write-Host '0) Выход'
    $choice = Read-Host 'Выберите пункт'
    switch($choice){
      '1' { Start-Server }
      '2' { Restart-Server }
      '3' { Stop-Server }
      '4' { Status-Server }
      '5' { Tail-Logs }
      '6' { $msg = Read-Host 'Комментарий к миграции'; if(-not $msg){ $msg='auto' }; $script:Message=$msg; DB-Migrate }
      '7' { DB-Upgrade }
      '8' { DB-Current }
      '9' { DB-Stamp }
      '0' { break }
      default { Write-Warn 'Неизвестная команда' }
    }
  }
}

switch($Action){
  'start'   { Start-Server }
  'stop'    { Stop-Server }
  'restart' { Restart-Server }
  'status'  { Status-Server }
  'tail'    { Tail-Logs }
  'dbinit'  { DB-Init }
  'dbmigrate' { DB-Migrate }
  'dbupgrade' { DB-Upgrade }
  'dbstamp' { DB-Stamp }
  'dbcurrent' { DB-Current }
  default   { Show-Menu }
}
