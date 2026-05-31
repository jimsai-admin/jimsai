# deploy-lambda-zip.ps1
# Deploys JimsAI API Gateway to AWS Lambda using a zip package (no Docker required)
# Usage: .\deploy-lambda-zip.ps1 -Region us-east-1 -FunctionName jimsai-api-gateway -CorsAllowOrigin https://jimsai.vercel.app

param(
    [string]$Region = "us-east-1",
    [string]$FunctionName = "jimsai-api-gateway",
    [string]$CorsAllowOrigin = "https://jimsai.vercel.app",
    [string]$Runtime = "python3.11",
    [string]$MemorySize = "512",
    [string]$Timeout = "30"
)

$ErrorActionPreference = "Stop"
$RootDir = "C:\Users\ajibe\Jims-AI"
$ServiceDir = "$RootDir\services\api-gateway"
$BuildDir = "$RootDir\.lambda-build"
$ZipPath = "$RootDir\lambda-package.zip"
$AccountId = (aws sts get-caller-identity --query Account --output text)
$RoleName = "$FunctionName-role"
$RoleArn = "arn:aws:iam::${AccountId}:role/$RoleName"

Write-Host "`n=== JimsAI Lambda Zip Deploy ===" -ForegroundColor Cyan
Write-Host "Region:   $Region"
Write-Host "Function: $FunctionName"
Write-Host "Account:  $AccountId"
Write-Host "CORS:     $CorsAllowOrigin`n"

# ── Step 1: Clean build dir ──────────────────────────────────────────────────
Write-Host "[1/6] Cleaning build directory..." -ForegroundColor Yellow
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
New-Item -ItemType Directory -Path $BuildDir | Out-Null

# ── Step 2: Install dependencies ─────────────────────────────────────────────
Write-Host "[2/6] Installing dependencies into build directory..." -ForegroundColor Yellow
pip install `
    --target $BuildDir `
    --platform manylinux2014_x86_64 `
    --implementation cp `
    --python-version 3.11 `
    --only-binary=:all: `
    --upgrade `
    -r "$ServiceDir\requirements.lambda.txt"

if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# ── Step 3: Copy app code ─────────────────────────────────────────────────────
Write-Host "[3/6] Copying app code..." -ForegroundColor Yellow
Copy-Item -Recurse -Force "$ServiceDir\app" "$BuildDir\app"

# ── Step 4: Zip everything ────────────────────────────────────────────────────
Write-Host "[4/6] Creating zip package..." -ForegroundColor Yellow
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path "$BuildDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipSize = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host "    Package size: ${ZipSize} MB"

# ── Step 5: Ensure IAM role exists ───────────────────────────────────────────
Write-Host "[5/6] Checking IAM role..." -ForegroundColor Yellow
$roleExists = aws iam get-role --role-name $RoleName 2>$null
if (-not $roleExists) {
    Write-Host "    Creating IAM role $RoleName..."
    $trustPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    aws iam create-role `
        --role-name $RoleName `
        --assume-role-policy-document $trustPolicy | Out-Null
    aws iam attach-role-policy `
        --role-name $RoleName `
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole | Out-Null
    Write-Host "    Waiting for role to propagate..."
    Start-Sleep -Seconds 10
} else {
    Write-Host "    Role already exists, skipping."
}

# ── Step 6: Deploy Lambda function ───────────────────────────────────────────
Write-Host "[6/6] Deploying Lambda function..." -ForegroundColor Yellow

# Load env vars from .env file for Lambda environment
$envVars = @{}
Get-Content "$RootDir\.env" | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
        $envVars[$matches[1].Trim()] = $matches[2].Trim()
    }
}
# Add CORS origin
$envVars["CORS_ORIGINS"] = $CorsAllowOrigin

# Build environment variables string for AWS CLI
$envJson = ($envVars.GetEnumerator() | ForEach-Object { "`"$($_.Key)`":`"$($_.Value)`"" }) -join ","
$envJson = "{Variables:{$envJson}}"

$functionExists = aws lambda get-function --function-name $FunctionName --region $Region 2>$null

if (-not $functionExists) {
    Write-Host "    Creating new Lambda function..."
    aws lambda create-function `
        --function-name $FunctionName `
        --runtime $Runtime `
        --role $RoleArn `
        --handler app.lambda_handler.handler `
        --zip-file "fileb://$ZipPath" `
        --region $Region `
        --memory-size $MemorySize `
        --timeout $Timeout `
        --environment $envJson | Out-Null

    Write-Host "    Waiting for function to be active..."
    aws lambda wait function-active --function-name $FunctionName --region $Region

    Write-Host "    Adding Function URL..."
    $urlConfig = aws lambda create-function-url-config `
        --function-name $FunctionName `
        --auth-type NONE `
        --cors "{AllowOrigins:[$CorsAllowOrigin],AllowMethods:[*],AllowHeaders:[*]}" `
        --region $Region | ConvertFrom-Json

    # Allow public access
    aws lambda add-permission `
        --function-name $FunctionName `
        --statement-id FunctionURLAllowPublicAccess `
        --action lambda:InvokeFunctionUrl `
        --principal "*" `
        --function-url-auth-type NONE `
        --region $Region | Out-Null

} else {
    Write-Host "    Updating existing Lambda function..."
    aws lambda update-function-code `
        --function-name $FunctionName `
        --zip-file "fileb://$ZipPath" `
        --region $Region | Out-Null

    Write-Host "    Waiting for update to complete..."
    aws lambda wait function-updated --function-name $FunctionName --region $Region

    aws lambda update-function-configuration `
        --function-name $FunctionName `
        --environment $envJson `
        --region $Region | Out-Null

    $urlConfig = aws lambda get-function-url-config `
        --function-name $FunctionName `
        --region $Region 2>$null | ConvertFrom-Json
}

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host "`n=== Deploy Complete ===" -ForegroundColor Green

$functionUrl = $urlConfig.FunctionUrl
Write-Host "`nLambda Function URL: $functionUrl" -ForegroundColor Cyan
Write-Host "`nNext steps:"
Write-Host "  1. Test: curl ${functionUrl}health"
Write-Host "  2. Go to Vercel -> Settings -> Environment Variables"
Write-Host "     Set NEXT_PUBLIC_API_BASE_URL = $functionUrl"
Write-Host "  3. Redeploy Vercel (Deployments -> Redeploy)"
Write-Host ""
