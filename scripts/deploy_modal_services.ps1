# Deploy all five Modal AI services sequentially.
# Run from the repo root: .\scripts\deploy_modal_services.ps1

$env:MODAL_TOKEN_ID = "ak-dnS5M0PACpkq73ysOPo9Wv"
$env:MODAL_TOKEN_SECRET = "as-PjOy3kJLzuv8UIqmOzYIlM"

$ROOT = $PSScriptRoot | Split-Path -Parent
Set-Location $ROOT

$services = @(
    "modal/modal_embedding_service.py",
    "modal/modal_classification_service.py",
    "modal/modal_intent_service.py",
    "modal/modal_renderer_service.py",
    "modal/modal_reasoning_service.py"
)

$urls = @{}

foreach ($svc in $services) {
    Write-Host "`n=== Deploying $svc ===" -ForegroundColor Cyan
    $output = modal deploy $svc 2>&1
    Write-Host $output
    # Extract the URL from modal deploy output
    $urlLine = $output | Where-Object { $_ -match "modal\.run" } | Select-Object -Last 1
    if ($urlLine -match "(https://\S+\.modal\.run)") {
        $url = $Matches[1]
        $urls[$svc] = $url
        Write-Host "  URL: $url" -ForegroundColor Green
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $svc (exit $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
    Write-Host "  OK" -ForegroundColor Green
}

Write-Host "`n=== Deployment complete ===" -ForegroundColor Green
Write-Host "URLs:"
foreach ($entry in $urls.GetEnumerator()) {
    Write-Host "  $($entry.Key): $($entry.Value)"
}
