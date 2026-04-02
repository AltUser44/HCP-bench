# Build the C++ hcp_worker (requires CMake and a C++17 toolchain).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$cpp = Join-Path $root "..\cpp"
Set-Location $cpp

if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
  Write-Error "cmake not found. Install CMake and add it to PATH."
}

New-Item -ItemType Directory -Force -Path build | Out-Null
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
Write-Host "Binary (typical): cpp\build\Release\hcp_worker.exe"
