$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskRuntimeFile = Join-Path $PSScriptRoot '.build-local\python-runtime-path.txt'
$taskPythonExe = $null
if (Test-Path -LiteralPath $taskRuntimeFile) {
    $taskCandidate = (Get-Content -LiteralPath $taskRuntimeFile -Raw).Trim()
    if (Test-Path -LiteralPath $taskCandidate) { $taskPythonExe = $taskCandidate }
}
if (-not $taskPythonExe) {
    $taskPythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($taskPythonCommand -and $taskPythonCommand.Source -notmatch 'Microsoft\\WindowsApps') { $taskPythonExe = $taskPythonCommand.Source }
}
if (-not $taskPythonExe) { throw 'Python wurde nicht gefunden.' }
$env:PYTHONPATH = Join-Path $PSScriptRoot '.build-local\python-packages'
$taskLocalBin = Join-Path $PSScriptRoot '.build-local\python-packages\bin'
$taskGitHubBin = Join-Path $PSScriptRoot '.build-local\tools\github-cli\bin'
$env:PATH = "$taskLocalBin;$taskGitHubBin;C:\Program Files\Git\cmd;" + $env:PATH
$env:PYTHONIOENCODING = 'utf-8'
$env:GH_CONFIG_DIR = Join-Path $PSScriptRoot '.build-local\auth\github'
$env:HF_HOME = Join-Path $PSScriptRoot '.build-local\auth\huggingface' 
& $taskPythonExe 'scripts\build_and_htmlize.py'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $taskPythonExe 'scripts\deploy_everywhere.py'
exit $LASTEXITCODE
