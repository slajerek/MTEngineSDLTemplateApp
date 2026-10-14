$ErrorActionPreference = 'Stop'
$Root = Resolve-Path "$PSScriptRoot\..\.."
$Header = Get-Content "$Root\src\TemplateAppVersion.h" -Raw
if ($Header -notmatch '#define\s+TEMPLATEAPP_VERSION\s+"([^"]+)"') { throw "no TEMPLATEAPP_VERSION in TemplateAppVersion.h" }
$Version = $Matches[1]
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'ARM64' } else { 'x64' }
$Prod = "$Root\platform\Windows\prod\$Arch"
if (-not (Test-Path "$Prod\LICENSES.txt")) { throw "no package in $Prod -- run .\build-windows.ps1 -Prod first" }
$Suffix = if (Get-ChildItem $Prod -Filter '*-nc.exe') { '-nc' } else { '' }
$Name = "MTEngineSDLTemplateApp-$Version-windows-$($Arch.ToLower())$Suffix"
New-Item -ItemType Directory -Force "$Root\releases" | Out-Null
$Stage = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid())
Copy-Item -Recurse $Prod "$Stage\$Name"
$Zip = "$Root\releases\$Name.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path "$Stage\$Name" -DestinationPath $Zip
Remove-Item -Recurse $Stage
"zip_path=$Zip"
if ($env:GITHUB_OUTPUT) { "zip_path=$Zip" | Out-File -Append -Encoding utf8 $env:GITHUB_OUTPUT }
