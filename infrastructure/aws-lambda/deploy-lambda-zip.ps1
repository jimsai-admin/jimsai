# deploy-lambda-zip.ps1
# Deploys JimsAI API Gateway to AWS Lambda using a zip package (no Docker required)
# Usage: .\deploy-lambda-zip.ps1 -Region us-east-1 -FunctionName jimsai-api-gateway -CorsAllowOrigin https://jimsai.vercel.app

param(
    [string]$Region = "us-east-1",
    [string]$FunctionName = "jimsai-api-gateway",
    [string]$CorsAllowOrigin = "https://jimsai.vercel.app",
    [string]$Runtime = "python3.11",
    [string]$MemorySize = "1536",
    [string]$Timeout = "120"
)

$ErrorActionPreference = "Stop"
$RootDir = "C:\Users\ajibe\Jims-AI"
$ServiceDir = "$RootDir\services\api-gateway"
$BuildDir = "$RootDir\.lambda-build"
$ZipPath = "$RootDir\infrastructure\aws-lambda\lambda-package.zip"
$DeployBucket = "jimsai-lambda-deploy-095931689519"
$DeployKey = "lambda-package.zip"
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
# pip streams progress to stderr; under $ErrorActionPreference='Stop', PowerShell 5.1
# wraps that as a terminating NativeCommandError even when pip exits 0. Run it under
# 'Continue' and gate on the REAL exit code (as the check below already intends).
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$prevProg = $ProgressPreference
$ProgressPreference = "SilentlyContinue"
pip install `
    --target $BuildDir `
    --platform manylinux2014_x86_64 `
    --implementation cp `
    --python-version 3.11 `
    --only-binary=:all: `
    --upgrade `
    --quiet --no-input `
    -r "$ServiceDir\requirements.lambda.txt"
$pipExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
$ProgressPreference = $prevProg

if ($pipExit -ne 0) { throw "pip install failed (exit $pipExit)" }

# ── Step 3: Copy app code ─────────────────────────────────────────────────────
Write-Host "[3/6] Copying app code..." -ForegroundColor Yellow
Remove-Item -Recurse -Force "$BuildDir\app" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$BuildDir\prototype" -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force "$ServiceDir\app" "$BuildDir\app"
Copy-Item -Recurse -Force "$RootDir\prototype" "$BuildDir\prototype"

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
$rawEnv = @{}
Get-Content "$RootDir\.env" | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
        $rawEnv[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$allowedKeys = @(
    "JIMS_STORAGE_BACKEND",
    "JIMS_STRICT_PROVIDER_STARTUP",
    "JIMS_AUTH_PROVIDER",
    "JIMS_AUTH_REQUIRED",
    "JIMS_SUPABASE_DEFAULT_SCOPES",
    "JIMS_GRAPH_PROVIDER",
    "JIMS_ENABLE_NEO4J",
    "JIMS_CLOUD_AUTHORITATIVE",
    "JIMS_EMBEDDING_SERVICE_URL",
    "JIMS_EMBEDDING_SERVICE_TOKEN",
    "JIMS_LLM_PROVIDER",
    "JIMS_ENABLE_LOCAL_QWEN",
    "JIMS_QWEN_SERVICE_URL",
    "JIMS_QWEN_SERVICE_TOKEN",
    "JIMS_QWEN_MODEL",
    "JIMS_LOCAL_INFERENCE_URL",
    "JIMS_LOCAL_INFERENCE_API_KEY",
    "JIMS_LOCAL_INFERENCE_MODEL",
    "JIMS_LOCAL_INFERENCE_CHAT_PATH",
    "JIMS_LOCAL_INFERENCE_TIMEOUT",
    "JIMS_LOCAL_RENDER_MODEL",
    "JIMS_LOCAL_RENDER_CHAT_PATH",
    "JIMS_LOCAL_RENDER_TIMEOUT",
    "JIMS_RENDER_MODEL_NAME",
    "JIMS_RENDER_MODEL_REPO",
    "JIMS_RENDER_MODEL_FILE",
    "JIMS_RENDER_CONTEXT",
    "JIMS_RENDER_MAX_TOKENS",
    "JIMS_RENDER_BATCH",
    "JIMS_RENDER_THREADS",
    "JIMS_ENABLE_MULTIMODAL_ENCODERS",
    "JIMS_MULTIMODAL_ENCODER_MODE",
    "JIMS_MULTIMODAL_ENCODER_URL",
    "JIMS_MULTIMODAL_ENCODER_API_KEY",
    "JIMS_LIVE_EMBEDDING_TIMEOUT",
    "JIMS_LIVE_EMBEDDING_ATTEMPTS",
    "JIMS_INTENT_EMBEDDING_TIMEOUT",
    "JIMS_PROVIDER_HTTP_TIMEOUT",
    "JIMS_PROVIDER_CHECK_TIMEOUT",
    "JIMS_USE_LOCAL_SENTENCE_TRANSFORMERS",
    "JIMS_RUNTIME_CACHE_VERSION",
    "JIMS_ENABLE_SEMANTIC_CAPABILITY_ROUTER",
    "JIMS_ENABLE_ZERO_SHOT_CAPABILITY_ROUTER",
    "JIMS_ENABLE_LLM_CAPABILITY_ROUTER",
    "JIMS_CAPABILITY_EMBEDDING_SERVICE_URL",
    "JIMS_CAPABILITY_EMBEDDING_SERVICE_TOKEN",
    "JIMS_CAPABILITY_CLASSIFIER_URL",
    "JIMS_CAPABILITY_CLASSIFIER_TOKEN",
    "JIMS_CAPABILITY_CLASSIFIER_TIMEOUT",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "REDIS_URL",
    "REDIS_PUBLIC_ENDPOINT",
    "REDIS_API",
    "JIMS_CELERY_KEY_PREFIX",
    "CF_ACCOUNT_ID",
    "CF_R2_BUCKET",
    "CF_R2_ACCESS_KEY",
    "CF_R2_SECRET_KEY",
    "CF_VECTORIZE_INDEX",
    "CF_VECTORIZE_API_TOKEN",
    "CF_VECTORIZE_DIMENSIONS",
    "KAGGLE_USERNAME",
    "KAGGLE_API_TOKEN",
    "KAGGLE_DATASET_OWNER",
    "LOG_LEVEL"
)

$envVars = @{}
foreach ($key in $allowedKeys) {
    if ($rawEnv.ContainsKey($key) -and $rawEnv[$key]) {
        $envVars[$key] = $rawEnv[$key]
    }
}

$envVars["JIMS_STORAGE_BACKEND"] = "production"
$envVars["JIMS_STRICT_PROVIDER_STARTUP"] = "false"
$envVars["JIMS_AUTH_PROVIDER"] = "supabase"
$envVars["JIMS_AUTH_REQUIRED"] = "true"
$envVars["JIMS_LLM_PROVIDER"] = "local"
$envVars["JIMS_ENABLE_LOCAL_QWEN"] = "true"
$envVars["JIMS_ENABLE_GROQ_T1"] = "false"
$envVars["JIMS_ENABLE_GROQ_T2"] = "false"
$envVars["JIMS_ENABLE_GROQ_CANVAS"] = "false"
$envVars["JIMS_ENABLE_GROQ_INVENTION"] = "false"
$envVars["JIMS_ALLOW_EXTERNAL_GROQ"] = "false"
# T1 threshold: T2 remains required for query rendering.
$envVars["JIMS_T1_SKIP_CONFIDENCE"] = "0.60"
$envVars["JIMS_ADAPTIVE_TRANSFORMER_THINNING"] = "true"
$envVars["JIMS_CAUSAL_TRAVERSAL_DEPTH"] = "4"
# Resolution learning: only write back verified high-quality results
$envVars["JIMS_ENABLE_RESOLUTION_LEARNING"] = "true"
$envVars["JIMS_RESOLUTION_LEARNING_MIN_CONFIDENCE"] = "0.90"
# Embedding timeout: allow 45s for HF Space on cold outbound connection
$envVars["JIMS_MULTIMODAL_ENCODER_TIMEOUT"] = "45"
$envVars["JIMS_LIVE_EMBEDDING_TIMEOUT"] = "6"
$envVars["JIMS_LIVE_EMBEDDING_ATTEMPTS"] = "1"
$envVars["JIMS_INTENT_EMBEDDING_TIMEOUT"] = "4"
$envVars["JIMS_PROVIDER_HTTP_TIMEOUT"] = "6"
$envVars["JIMS_PROVIDER_CHECK_TIMEOUT"] = "4"
$envVars["JIMS_USE_LOCAL_SENTENCE_TRANSFORMERS"] = "false"
$envVars["JIMS_RUNTIME_CACHE_VERSION"] = "2026-06-06-latency-math-v3"
# Add CORS origin
$envVars["CORS_ORIGINS"] = $CorsAllowOrigin

$environmentPath = Join-Path $env:TEMP "jimsai-lambda-env.json"
$envJson = @{ Variables = $envVars } | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($environmentPath, $envJson, (New-Object System.Text.UTF8Encoding($false)))

$functionExists = aws lambda get-function --function-name $FunctionName --region $Region 2>$null

if (-not $functionExists) {
    Write-Host "    Creating new Lambda function..."
    Write-Host "    Uploading package to s3://$DeployBucket/$DeployKey..."
    aws s3 cp $ZipPath "s3://$DeployBucket/$DeployKey" --region $Region | Out-Null

    aws lambda create-function `
        --function-name $FunctionName `
        --runtime $Runtime `
        --role $RoleArn `
        --handler app.lambda_handler.handler `
        --code "S3Bucket=$DeployBucket,S3Key=$DeployKey" `
        --region $Region `
        --memory-size $MemorySize `
        --timeout $Timeout `
        --environment "file://$environmentPath" | Out-Null

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
    Write-Host "    Uploading package to s3://$DeployBucket/$DeployKey..."
    aws s3 cp $ZipPath "s3://$DeployBucket/$DeployKey" --region $Region | Out-Null

    aws lambda update-function-code `
        --function-name $FunctionName `
        --s3-bucket $DeployBucket `
        --s3-key $DeployKey `
        --region $Region | Out-Null

    Write-Host "    Waiting for update to complete..."
    aws lambda wait function-updated --function-name $FunctionName --region $Region

    aws lambda update-function-configuration `
        --function-name $FunctionName `
        --environment "file://$environmentPath" `
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
