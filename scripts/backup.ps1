# 投资雷达 · 每日备份 radar.db（保留最近 14 份，含完整性校验与恢复演练）
$ErrorActionPreference = "Continue"
$src = "C:\Users\32333\Desktop\project\money\data\radar.db"
$dstDir = "C:\Users\32333\Desktop\project\money\data\backups"
New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
Set-Location "C:\Users\32333\Desktop\project\money"

# WAL checkpoint：把 -wal 合并进主库再拷贝
python -c "from invest_radar import store; store.init(); store.conn().execute('PRAGMA wal_checkpoint(TRUNCATE)')" 2>$null | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$dst = "$dstDir\radar_$stamp.db"
Copy-Item $src $dst -Force

# ===== M1: 完整性校验 + 恢复演练（不是只看文件存在）=====
$verify = python -c @"
import sqlite3, sys
db = r'$dst'
try:
    c = sqlite3.connect(db)
    integ = c.execute('PRAGMA integrity_check').fetchone()[0]
    stocks = c.execute('SELECT COUNT(*) FROM stock').fetchone()[0]
    watch = c.execute('SELECT COUNT(*) FROM watch').fetchone()[0]
    entries = c.execute('SELECT COUNT(*) FROM entry').fetchone()[0]
    ai = c.execute('SELECT COUNT(*) FROM entry_ai').fetchone()[0]
    c.close()
    ok = integ == 'ok' and stocks > 0 and watch > 0
    print(f'{integ}|{stocks}|{watch}|{entries}|{ai}|{1 if ok else 0}')
except Exception as e:
    print(f'ERROR|{e}|0|0|0|0')
"@
Write-Host "verify: $verify"
if ($verify -notmatch '\|1$') {
    Write-Host "!!! 备份校验失败，保留文件以便排查: $dst"
    exit 1
}

# 保留最近 14 份
Get-ChildItem $dstDir -Filter "radar_*.db" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -Skip 14 |
  Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "backup ok: radar_$stamp.db ($verify)"
