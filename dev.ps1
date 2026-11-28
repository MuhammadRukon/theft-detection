# Starts MediaMTX, the FastAPI server and the Vite dev server. Ctrl+C stops all three.
# -Record also saves the published webcam stream (see docs\recording-clips.md).
[CmdletBinding()]  # a mistyped switch is an error, not a silent unrecorded run
param([switch]$Record)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$mtx = Join-Path $root 'infra\bin\mediamtx.exe'

if (-not (Test-Path $mtx)) {
    Write-Error ("infra\bin\mediamtx.exe not found. The binary is gitignored. Download " +
        "mediamtx_v1.21.4_windows_amd64.zip from https://github.com/bluenviron/mediamtx/releases " +
        "and extract mediamtx.exe into infra\bin\.")
    exit 1
}

function Start-Child($file, $argList, $dir) {
    Start-Process -FilePath $file -ArgumentList $argList -WorkingDirectory $dir -NoNewWindow -PassThru
}

$procs = @()
$prevRecord = $env:MTX_PATHS_CAM1_RECORD
try {
    # Always set, so a value left in this window cannot turn recording on.
    $env:MTX_PATHS_CAM1_RECORD = if ($Record) { 'yes' } else { 'no' }
    if ($Record) { Write-Host 'RECORDING ON: the cam1 stream is saved to server\data\recordings\cam1\' }
    $procs += Start-Child $mtx 'infra\mediamtx.yml' $root
    $procs += Start-Child 'uv' 'run uvicorn app.main:app --host 127.0.0.1 --port 8000' (Join-Path $root 'server')
    $procs += Start-Child 'bun' 'run dev --host 127.0.0.1 --strictPort' (Join-Path $root 'client')
    Write-Host 'Running: MediaMTX, server :8000, client http://127.0.0.1:5173. Ctrl+C to stop.'
    while (-not ($procs | Where-Object HasExited)) { Start-Sleep -Seconds 1 }
    Write-Warning 'A child process exited; stopping the rest.'
}
finally {
    # /T kills the tree: uv and bun spawn python and node children.
    foreach ($p in $procs) { if (-not $p.HasExited) { taskkill /PID $p.Id /T /F | Out-Null } }
    $env:MTX_PATHS_CAM1_RECORD = $prevRecord  # $null removes the variable
}
