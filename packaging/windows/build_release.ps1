param(
    [string]$Version = "0.2.4-beta",
    [string]$MsiVersion = "0.2.4",
    [switch]$Offline,
    [string]$Wheelhouse = "",
    [string]$FfmpegDir = "",
    [string]$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    [switch]$SkipFfmpegDownload,
    [string]$DenoDir = "",
    [string]$DenoUrl = "",
    [switch]$SkipDenoDownload,
    [switch]$SkipMsi
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$ReleaseDir = Join-Path $RootDir "dist\release"
$AppDir = Join-Path $RootDir "dist\windows\YouTubeHarvester"
$PortableZip = Join-Path $ReleaseDir "YouTubeHarvester_${Version}_windows_portable.zip"
$InnoScript = Join-Path $ScriptDir "YouTubeHarvester.iss"
$WixProduct = Join-Path $ScriptDir "Product.wxs"
$WixObjDir = Join-Path $RootDir "dist\wix-obj"
$HarvestedWxs = Join-Path $WixObjDir "harvested.wxs"
$GeneratedWixSource = Join-Path $WixObjDir "Product.wix7.wxs"

function ConvertTo-WixXmlText {
    param([string]$Value)
    return [System.Security.SecurityElement]::Escape($Value)
}

function New-WixSafeId {
    param(
        [string]$Prefix,
        [string]$Value
    )
    $hash = [System.Security.Cryptography.SHA1]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $digest = -join ($hash.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") })
    return "${Prefix}_$($digest.Substring(0, 16))"
}

function Join-OptionalPath {
    param(
        [string]$BasePath,
        [string]$ChildPath
    )
    if ([string]::IsNullOrWhiteSpace($BasePath)) {
        return $null
    }
    return Join-Path $BasePath $ChildPath
}

function Find-ToolPath {
    param(
        [string]$CommandName,
        [string[]]$CandidatePaths
    )

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    foreach ($candidate in $CandidatePaths) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Get-Item $candidate).FullName
        }
    }

    return $null
}

function Invoke-NativeChecked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Try-AcceptWix7Eula {
    param([string]$WixPath)

    try {
        & $WixPath "eula" "accept" "wix7"
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not auto-accept WiX v7 OSMF/EULA terms; MSI build may be skipped."
        }
    } catch {
        Write-Warning "Could not auto-accept WiX v7 OSMF/EULA terms: $_"
    }
}

function Add-WixDirectoryXml {
    param(
        [System.Text.StringBuilder]$Builder,
        [System.IO.DirectoryInfo]$Directory,
        [string]$DirectoryId,
        [string]$Indent,
        [System.Collections.Generic.List[string]]$ComponentIds
    )

    foreach ($file in (Get-ChildItem -LiteralPath $Directory.FullName -File | Sort-Object Name)) {
        $componentId = New-WixSafeId "cmp" $file.FullName
        $fileId = New-WixSafeId "fil" $file.FullName
        $ComponentIds.Add($componentId) | Out-Null
        [void]$Builder.AppendLine("${Indent}<Component Id=`"$componentId`" Guid=`"*`">")
        [void]$Builder.AppendLine("${Indent}  <File Id=`"$fileId`" Source=`"$(ConvertTo-WixXmlText $file.FullName)`" KeyPath=`"yes`" />")
        [void]$Builder.AppendLine("${Indent}</Component>")
    }

    foreach ($child in (Get-ChildItem -LiteralPath $Directory.FullName -Directory | Sort-Object Name)) {
        $childId = New-WixSafeId "dir" $child.FullName
        [void]$Builder.AppendLine("${Indent}<Directory Id=`"$childId`" Name=`"$(ConvertTo-WixXmlText $child.Name)`">")
        Add-WixDirectoryXml -Builder $Builder -Directory $child -DirectoryId $childId -Indent "${Indent}  " -ComponentIds $ComponentIds
        [void]$Builder.AppendLine("${Indent}</Directory>")
    }
}

function Write-Wix7Source {
    param(
        [string]$AppDir,
        [string]$OutputPath,
        [string]$MsiVersion
    )

    $componentIds = [System.Collections.Generic.List[string]]::new()
    $builder = [System.Text.StringBuilder]::new()
    $appDirectory = Get-Item -LiteralPath $AppDir

    [void]$builder.AppendLine('<?xml version="1.0" encoding="UTF-8"?>')
    [void]$builder.AppendLine('<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">')
    [void]$builder.AppendLine("  <Package Name=`"YouTube Harvester`" Manufacturer=`"YouTube Harvester`" Version=`"$MsiVersion`" UpgradeCode=`"B2DBF6B2-9429-45F9-B84D-1C74B33F0F70`" Scope=`"perMachine`">")
    [void]$builder.AppendLine('    <MajorUpgrade DowngradeErrorMessage="A newer version of YouTube Harvester is already installed." />')
    [void]$builder.AppendLine('    <MediaTemplate EmbedCab="yes" />')
    [void]$builder.AppendLine('    <StandardDirectory Id="ProgramFiles64Folder">')
    [void]$builder.AppendLine('      <Directory Id="INSTALLFOLDER" Name="YouTube Harvester">')
    Add-WixDirectoryXml -Builder $builder -Directory $appDirectory -DirectoryId "INSTALLFOLDER" -Indent "        " -ComponentIds $componentIds
    [void]$builder.AppendLine('      </Directory>')
    [void]$builder.AppendLine('    </StandardDirectory>')
    [void]$builder.AppendLine('    <StandardDirectory Id="ProgramMenuFolder">')
    [void]$builder.AppendLine('      <Directory Id="ApplicationProgramsFolder" Name="YouTube Harvester">')
    [void]$builder.AppendLine('        <Component Id="ApplicationShortcut" Guid="2B81E2AD-B599-4018-9A70-9770B994BA25">')
    [void]$builder.AppendLine('          <Shortcut Id="ApplicationStartMenuShortcut" Name="YouTube Harvester" Description="YouTube Harvester" Target="[INSTALLFOLDER]YouTubeHarvester.exe" WorkingDirectory="INSTALLFOLDER" />')
    [void]$builder.AppendLine('          <RemoveFolder Id="ApplicationProgramsFolder" On="uninstall" />')
    [void]$builder.AppendLine('          <RegistryValue Root="HKCU" Key="Software\YouTube Harvester" Name="installed" Type="integer" Value="1" KeyPath="yes" />')
    [void]$builder.AppendLine('        </Component>')
    [void]$builder.AppendLine('      </Directory>')
    [void]$builder.AppendLine('    </StandardDirectory>')
    [void]$builder.AppendLine('    <Feature Id="DefaultFeature" Title="YouTube Harvester" Level="1">')
    foreach ($componentId in $componentIds) {
        [void]$builder.AppendLine("      <ComponentRef Id=`"$componentId`" />")
    }
    [void]$builder.AppendLine('      <ComponentRef Id="ApplicationShortcut" />')
    [void]$builder.AppendLine('    </Feature>')
    [void]$builder.AppendLine('  </Package>')
    [void]$builder.AppendLine('</Wix>')

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
    $builder.ToString() | Set-Content -Encoding utf8 $OutputPath
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

$buildWindowsScript = Join-Path $ScriptDir "build_windows.ps1"
$buildWindowsArgs = @()
if ($Offline -or $Wheelhouse) {
    $buildWindowsArgs += @("-Offline", "-Wheelhouse", "$Wheelhouse")
} else {
    $buildWindowsArgs = @()
}
if (-not [string]::IsNullOrWhiteSpace($FfmpegDir)) {
    $buildWindowsArgs += @("-FfmpegDir", "$FfmpegDir")
}
if (-not [string]::IsNullOrWhiteSpace($FfmpegUrl)) {
    $buildWindowsArgs += @("-FfmpegUrl", "$FfmpegUrl")
}
if ($SkipFfmpegDownload) {
    $buildWindowsArgs += "-SkipFfmpegDownload"
}
if (-not [string]::IsNullOrWhiteSpace($DenoDir)) {
    $buildWindowsArgs += @("-DenoDir", "$DenoDir")
}
if (-not [string]::IsNullOrWhiteSpace($DenoUrl)) {
    $buildWindowsArgs += @("-DenoUrl", "$DenoUrl")
}
if ($SkipDenoDownload) {
    $buildWindowsArgs += "-SkipDenoDownload"
}
& $buildWindowsScript @buildWindowsArgs
if (-not $?) {
    throw "Windows application build failed."
}

if (-not (Test-Path (Join-Path $AppDir "YouTubeHarvester.exe"))) {
    throw "PyInstaller output was not found: $AppDir"
}

if (Test-Path $PortableZip) {
    Remove-Item $PortableZip -Force
}
Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $PortableZip -Force
Write-Host "Portable ZIP: $PortableZip"

$isccPath = Find-ToolPath "ISCC.exe" @(
    (Join-OptionalPath ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-OptionalPath $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
if ($isccPath) {
    Invoke-NativeChecked $isccPath @(
        "/DAppVersion=$Version",
        "/DSourceDir=$AppDir",
        "/DOutputDir=$ReleaseDir",
        "$InnoScript"
    )
} else {
    Write-Warning "Inno Setup was not found; Windows setup EXE was not built."
}

$wixPath = Find-ToolPath "wix.exe" @(
    (Join-OptionalPath $env:ProgramFiles "WiX Toolset v7\bin\wix.exe"),
    (Join-OptionalPath ${env:ProgramFiles(x86)} "WiX Toolset v7\bin\wix.exe")
)
$heatPath = Find-ToolPath "heat.exe" @(
    (Join-OptionalPath ${env:ProgramFiles(x86)} "WiX Toolset v3.11\bin\heat.exe"),
    (Join-OptionalPath $env:ProgramFiles "WiX Toolset v3.11\bin\heat.exe")
)
$candlePath = Find-ToolPath "candle.exe" @(
    (Join-OptionalPath ${env:ProgramFiles(x86)} "WiX Toolset v3.11\bin\candle.exe"),
    (Join-OptionalPath $env:ProgramFiles "WiX Toolset v3.11\bin\candle.exe")
)
$lightPath = Find-ToolPath "light.exe" @(
    (Join-OptionalPath ${env:ProgramFiles(x86)} "WiX Toolset v3.11\bin\light.exe"),
    (Join-OptionalPath $env:ProgramFiles "WiX Toolset v3.11\bin\light.exe")
)
if ($SkipMsi) {
    Write-Warning "MSI build was skipped by -SkipMsi."
} elseif ($wixPath) {
    try {
        Try-AcceptWix7Eula $wixPath
        Write-Wix7Source -AppDir $AppDir -OutputPath $GeneratedWixSource -MsiVersion $MsiVersion
        Write-Host "Building MSI with WiX Toolset 7."
        Invoke-NativeChecked $wixPath @(
            "build",
            "$GeneratedWixSource",
            "-arch", "x64",
            "-o", (Join-Path $ReleaseDir "YouTubeHarvester_${Version}_windows_x64.msi")
        )
    } catch {
        Write-Warning "Windows MSI was not built: $_"
    }
} elseif ($heatPath -and $candlePath -and $lightPath) {
    try {
        New-Item -ItemType Directory -Force -Path $WixObjDir | Out-Null
        Invoke-NativeChecked $heatPath @(
            "dir", "$AppDir",
            "-cg", "AppFiles",
            "-dr", "INSTALLFOLDER",
            "-srd",
            "-sreg",
            "-gg",
            "-var", "var.AppDir",
            "-out", "$HarvestedWxs"
        )
        Invoke-NativeChecked $candlePath @(
            "-dAppDir=$AppDir",
            "-dMsiVersion=$MsiVersion",
            "-out", "$WixObjDir\",
            "$WixProduct",
            "$HarvestedWxs"
        )
        Invoke-NativeChecked $lightPath @(
            "-ext", "WixUIExtension",
            "-out", (Join-Path $ReleaseDir "YouTubeHarvester_${Version}_windows_x64.msi"),
            (Join-Path $WixObjDir "Product.wixobj"),
            (Join-Path $WixObjDir "harvested.wixobj")
        )
    } catch {
        Write-Warning "Windows MSI was not built: $_"
    }
} else {
    Write-Warning "WiX Toolset was not found; Windows MSI was not built."
}

$releaseFileNames = @(
    "YouTubeHarvester_${Version}_windows_portable.zip",
    "YouTubeHarvester_${Version}_windows_setup.exe",
    "YouTubeHarvester_${Version}_windows_x64.msi"
)
$hashFiles = Get-ChildItem $ReleaseDir -File |
    Where-Object { $releaseFileNames -contains $_.Name } |
    Sort-Object Name
if ($hashFiles) {
    $hashLines = foreach ($file in $hashFiles) {
        $hash = Get-FileHash -Algorithm SHA256 $file.FullName
        "$($hash.Hash.ToLower())  $($file.Name)"
    }
    $hashLines | Set-Content -Encoding ascii (Join-Path $ReleaseDir "SHA256SUMS-windows.txt")
}

Write-Host ""
Write-Host "Windows release files are in: $ReleaseDir"
