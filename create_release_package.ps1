$ErrorActionPreference = 'Stop'

# Use D drive for any temp files (avoid C:)
$Env:TEMP = "D:\PythonProject3\.venv"
$Env:TMP  = "D:\PythonProject3\.venv"

$Src      = "d:\PythonProject3\.venv"
$ZipPath  = "d:\project_release_20260909.zip"

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($ZipPath, 'Create')

$excludeDirs = @(
    '__pycache__','_merge_other','_backup_merged','.venv','Lib','Scripts',
    'include','share','build','dist','.workbuddy','temp_package_check',
    'temp_stage_pack','backup_2026-05-09','Log','logs','_mobile_test'
)
$excludeFiles = @(
    'api_key.local','deploy_upload.zip','project_full_20260904.zip',
    'project_release_20260909.zip','project_full_20260909.zip',
    'pyvenv.cfg','CACHEDIR.TAG','flask_err.log','flask_out.log',
    '灵智尚人_云服务器部署包.zip','README_20260904155847.md','README_20260904155849.md'
)
$exts = @('.py','.txt','.yml','.yaml','.css','.js','.html','.json','.sh',
          '.bat','.md','.png','.jpg','.jpeg','.gif','.svg','.ico',
          '.woff','.woff2','.ttf','.spec')

$count = 0
Get-ChildItem $Src -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring($Src.Length + 1)
    $skip = $false

    foreach ($ed in $excludeDirs) {
        if ($rel -match "(^|[\\/])$([regex]::Escape($ed))([\\/]|`$)") { $skip = $true; break }
    }
    if (-not $skip) {
        foreach ($ef in $excludeFiles) {
            if ($_.Name -eq $ef) { $skip = $true; break }
        }
    }
    if (-not $skip -and ($_.Extension -in $exts -or $_.Name -eq 'Dockerfile')) {
        try {
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $rel.Replace('\','/')) | Out-Null
            $count++
        } catch { }
    }
}
$zip.Dispose()

$size = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  打包完成" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  文件路径: $ZipPath"
Write-Host "  文件数量: $count"
Write-Host "  压缩包大小: $size MB"
