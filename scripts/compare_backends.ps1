# Compare Python vs C++ workers on loopback (same scenarios, two JSON reports).
# Requires: pip install -e .  and  a built cpp/build/.../hcp_worker.exe
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

New-Item -ItemType Directory -Force -Path "out" | Out-Null

Write-Host "=== Python worker ===" -ForegroundColor Cyan
python -m hcpbench run examples/benchmark.yaml -o out/report_python.json

$cppExe = Join-Path $root "cpp\build\Release\hcp_worker.exe"
if (-not (Test-Path $cppExe)) {
  Write-Host ""
  Write-Host "Skip C++ report: not found: $cppExe" -ForegroundColor Yellow
  Write-Host "Build with: cmake -B cpp/build && cmake --build cpp/build --config Release"
  exit 0
}

Write-Host ""
Write-Host "=== C++ worker ===" -ForegroundColor Cyan
python -m hcpbench run examples/benchmark_cpp.yaml -o out/report_cpp.json

Write-Host ""
Write-Host "Reports: out\report_python.json  out\report_cpp.json" -ForegroundColor Green
