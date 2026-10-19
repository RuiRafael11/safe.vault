param(
    [string]$Python = "python",
    [string]$OutputDirectory = "outputs"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    $sourcePath = Join-Path $projectRoot "src"
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = $sourcePath + [IO.Path]::PathSeparator + $env:PYTHONPATH
    }
    else {
        $env:PYTHONPATH = $sourcePath
    }

    $version = (& $Python -c "from cofre_local import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
        throw "Não foi possível obter uma versão válida de cofre_local.__version__."
    }
    $fileVersion = "$version.0"

    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Os testes falharam; o executável não foi criado."
    }

    & $Python -c "from flet_cli.cli import main; main()" pack run_cofre.py `
        --name CofreLocal `
        --icon assets\cofre_local.ico `
        --distpath dist `
        --add-data assets:assets `
        --product-name "Cofre Local" `
        --file-description "Gestor de palavras-passe offline" `
        --product-version $version `
        --file-version $fileVersion `
        --company-name "Cofre Local" `
        --copyright "Copyright 2026" `
        --hidden-import cofre_local.app cofre_local.ui_flet.app `
            cofre_local.ui_flet.components cofre_local.ui_flet.motion `
            cofre_local.ui_flet.preferences cofre_local.ui_flet.theme `
            cofre_local.vault `
        --yes
    if ($LASTEXITCODE -ne 0) {
        throw "O empacotamento terminou com o código $LASTEXITCODE."
    }

    $artifact = Join-Path $projectRoot "dist\CofreLocal.exe"
    if (-not (Test-Path -LiteralPath $artifact)) {
        throw "O empacotamento não produziu dist\CofreLocal.exe."
    }
    $releaseDirectory = Join-Path $projectRoot $OutputDirectory
    New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
    $releaseArtifact = Join-Path $releaseDirectory "CofreLocal.exe"
    Copy-Item -LiteralPath $artifact -Destination $releaseArtifact -Force
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $releaseArtifact).Hash.ToLowerInvariant()
    Set-Content -LiteralPath (Join-Path $releaseDirectory "CofreLocal-SHA256.txt") -Value "$hash  CofreLocal.exe" -NoNewline
    $metadata = [ordered]@{
        product = "Cofre Local"
        version = $version
        file_version = $fileVersion
        artifact = "CofreLocal.exe"
        sha256 = $hash
        built_at_utc = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json
    Set-Content -LiteralPath (Join-Path $releaseDirectory "CofreLocal-version.json") -Value $metadata -NoNewline
}
finally {
    Pop-Location
}
