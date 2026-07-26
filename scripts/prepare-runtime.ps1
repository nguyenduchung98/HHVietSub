$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$cacheRoot = Join-Path $projectRoot '.runtime-cache'
$pythonDir = Join-Path $projectRoot 'runtime\python'
$ffmpegDir = Join-Path $projectRoot 'vendor\ffmpeg'

$pythonVersion = '3.12.10'
$pythonArchive = Join-Path $cacheRoot "python-$pythonVersion-embed-amd64.zip"
$pythonUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip"
$ffmpegArchive = Join-Path $cacheRoot 'ffmpeg-release-essentials.zip'
$ffmpegUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'

New-Item -ItemType Directory -Force -Path $cacheRoot, $pythonDir, $ffmpegDir | Out-Null

function Get-Archive([string]$Url, [string]$Destination) {
  if (Test-Path -LiteralPath $Destination) {
    Write-Host "[runtime] Using cache: $Destination"
    return
  }
  Write-Host "[runtime] Downloading: $Url"
  Invoke-WebRequest -Uri $Url -OutFile $Destination
}

if (-not (Test-Path -LiteralPath (Join-Path $pythonDir 'python.exe'))) {
  Get-Archive $pythonUrl $pythonArchive
  Write-Host '[runtime] Extracting Python Embeddable...'
  Expand-Archive -LiteralPath $pythonArchive -DestinationPath $pythonDir -Force
}

if (-not (Test-Path -LiteralPath (Join-Path $ffmpegDir 'ffmpeg.exe')) -or
    -not (Test-Path -LiteralPath (Join-Path $ffmpegDir 'ffprobe.exe'))) {
  Get-Archive $ffmpegUrl $ffmpegArchive
  $extractDir = Join-Path $cacheRoot 'ffmpeg-extracted'
  if (Test-Path -LiteralPath $extractDir) {
    Remove-Item -LiteralPath $extractDir -Recurse -Force
  }
  Expand-Archive -LiteralPath $ffmpegArchive -DestinationPath $extractDir -Force
  $binDir = Get-ChildItem -LiteralPath $extractDir -Directory |
    ForEach-Object { Join-Path $_.FullName 'bin' } |
    Where-Object { Test-Path -LiteralPath (Join-Path $_ 'ffmpeg.exe') } |
    Select-Object -First 1
  if (-not $binDir) {
    throw 'FFmpeg bin directory was not found.'
  }
  Copy-Item -LiteralPath (Join-Path $binDir 'ffmpeg.exe') -Destination $ffmpegDir -Force
  Copy-Item -LiteralPath (Join-Path $binDir 'ffprobe.exe') -Destination $ffmpegDir -Force
  $license = Get-ChildItem -LiteralPath (Split-Path -Parent $binDir) -File |
    Where-Object { $_.Name -match '^(LICENSE|COPYING)' } |
    Select-Object -First 1
  if ($license) {
    Copy-Item -LiteralPath $license.FullName -Destination (Join-Path $ffmpegDir $license.Name) -Force
  }
}

& (Join-Path $pythonDir 'python.exe') --version
& (Join-Path $ffmpegDir 'ffmpeg.exe') -version | Select-Object -First 1
& (Join-Path $ffmpegDir 'ffprobe.exe') -version | Select-Object -First 1
Write-Host '[runtime] Python and FFmpeg are ready for packaging.'
