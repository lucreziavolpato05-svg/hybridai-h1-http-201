# Prepare the current PowerShell session for development on Windows.
#
#   . .\scripts\dev.ps1          # dot-source from the repository root
#   . .\scripts\dev.ps1 -NoSync  # skip `uv sync --locked`
#
# It leaves any other activated virtual environment, syncs and activates this
# project's .venv, and puts the pinned FrameX engine (.venv\bin\framex.exe,
# built by scripts/install-engine.sh) first on PATH and in FRAMEX_BINARY, so a
# stale global `framex` is never picked up. MSVC is only needed to rebuild the
# engine, not to run it.

param([switch]$NoSync)

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.venv'
$engine = Join-Path $venv 'bin\framex.exe'
Set-Location $root

# Leave a different venv (for example an old hybridai-h1 one) if it is active.
if ($env:VIRTUAL_ENV -and ((Resolve-Path $env:VIRTUAL_ENV -ErrorAction SilentlyContinue).Path -ne $venv)) {
    if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
}

if (-not $NoSync) {
    uv sync --locked
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'uv sync --locked failed; fix the message above (or use -NoSync) and rerun.'
        return
    }
}

$activate = Join-Path $venv 'Scripts\Activate.ps1'
if (-not (Test-Path $activate)) {
    Write-Warning "No virtual environment at $venv; run 'uv sync' first."
    return
}
. $activate

if (-not (Test-Path $engine)) {
    Remove-Item Env:FRAMEX_BINARY -ErrorAction SilentlyContinue
    Write-Warning "FrameX engine missing at $engine. Build it once with: sh scripts/install-engine.sh"
    return
}
$bin = Split-Path -Parent $engine
$env:PATH = "$bin;" + (($env:PATH -split ';' | Where-Object { $_ -and $_ -ne $bin }) -join ';')
$env:FRAMEX_BINARY = $engine

# The engine must come from the same commit as the Python client.
function Get-Rev($path, $pattern) {
    if (-not (Test-Path $path)) { return $null }
    $hit = Select-String -Path $path -Pattern $pattern | Select-Object -First 1
    if ($hit) { $hit.Matches[0].Groups[1].Value } else { $null }
}
$pinned = Get-Rev (Join-Path $root 'pyproject.toml') '^framex = \{.*rev = "([0-9a-f]+)"'
# Cargo records e.g. "framex 0.4.4 (git+https://...?rev=<sha>#<sha>)" = ["framex.exe"]
$built = Get-Rev (Join-Path $venv '.crates.toml') '^"framex .*#([0-9a-f]{40})\)"'
if ($pinned -and $built -ne $pinned) {
    Write-Warning "Engine was built from '$built' but pyproject.toml pins '$pinned'. Rebuild: sh scripts/install-engine.sh"
}

Write-Host ("Engine:  {0}  ({1})" -f (& $engine --version), $engine)
Write-Host ("Python:  {0}" -f (& python --version))
Write-Host 'Ready. Try: uv run pytest -q   |   uv run python src/main.py --repl'
