param(
    [string]$Region = "us-east-1",
    [string]$FunctionName = "jimsai-api-gateway",
    [string]$RepositoryName = "jimsai-api-gateway",
    [string]$ImageTag = "latest",
    [string]$RoleName = "jimsai-lambda-exec",
    [string]$EnvFile = ".env",
    [string]$CorsAllowOrigin = ""
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but was not found on PATH."
    }
}

function Read-DotEnv($Path) {
    $result = @{}
    if (-not (Test-Path $Path)) {
        throw "Environment file not found: $Path"
    }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $result[$key] = $value
    }
    return $result
}

Require-Command aws
Require-Command docker

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repoRoot

$accountId = aws sts get-caller-identity --query Account --output text
$registry = "$accountId.dkr.ecr.$Region.amazonaws.com"
$imageUri = "$registry/$RepositoryName`:$ImageTag"

aws ecr describe-repositories --region $Region --repository-names $RepositoryName *> $null
if ($LASTEXITCODE -ne 0) {
    aws ecr create-repository --region $Region --repository-name $RepositoryName *> $null
}

aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
docker build -f services/api-gateway/Dockerfile.lambda -t "$RepositoryName`:$ImageTag" .
docker tag "$RepositoryName`:$ImageTag" $imageUri
docker push $imageUri

$roleArn = aws iam get-role --role-name $RoleName --query "Role.Arn" --output text 2>$null
if ($LASTEXITCODE -ne 0 -or -not $roleArn) {
    $assumePolicyPath = Join-Path $env:TEMP "jimsai-lambda-assume-role.json"
    @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
"@ | Set-Content -Encoding UTF8 $assumePolicyPath
    $roleArn = aws iam create-role --role-name $RoleName --assume-role-policy-document "file://$assumePolicyPath" --query "Role.Arn" --output text
    aws iam attach-role-policy --role-name $RoleName --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    Start-Sleep -Seconds 12
}

$rawEnv = Read-DotEnv $EnvFile
$allowedKeys = @(
    "JIMS_STORAGE_BACKEND",
    "JIMS_STRICT_PROVIDER_STARTUP",
    "JIMS_AUTH_PROVIDER",
    "JIMS_AUTH_REQUIRED",
    "JIMS_SUPABASE_DEFAULT_SCOPES",
    "JIMS_GRAPH_PROVIDER",
    "JIMS_ENABLE_NEO4J",
    "JIMS_ENABLE_MULTIMODAL_ENCODERS",
    "JIMS_MULTIMODAL_ENCODER_MODE",
    "JIMS_MULTIMODAL_ENCODER_URL",
    "JIMS_MULTIMODAL_ENCODER_API_KEY",
    "JIMS_ENCODER_BASE_MODEL",
    "JIMS_SPPE_RENDERER_BASE_MODEL",
    "JIMS_AUTO_TRAINING_ENABLED",
    "JIMS_AUTO_TRAIN_MIN_SPPE_PAIRS",
    "JIMS_AUTO_TRAIN_MIN_SPPE_RENDER_PAIRS",
    "JIMS_AUTO_TRAIN_MIN_MEDIA_PENDING",
    "JIMS_AUTO_TRAIN_MIN_REVIEWED_PAIRS",
    "JIMS_AUTO_TRAIN_MAX_AMBIGUITY_PENDING",
    "JIMS_AUTO_TRAIN_MIN_RETRIEVAL_MISSES",
    "JIMS_ENABLE_GROQ_T1",
    "JIMS_ENABLE_GROQ_T2",
    "JIMS_ENABLE_GROQ_CANVAS",
    "JIMS_ENABLE_GROQ_INVENTION",
    "JIMS_ADAPTIVE_TRANSFORMER_THINNING",
    "JIMS_T1_SKIP_CONFIDENCE",
    "JIMS_T2_SKIP_CONFIDENCE",
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
    "GROQ_API_KEY",
    "GROQ_GENERATOR_MODEL",
    "GROQ_REASONING_MODEL",
    "GROQ_INTENT_MODEL",
    "GROQ_RENDER_MODEL",
    "GROQ_CANVAS_MODEL",
    "GROQ_INVENTION_MODEL",
    "LOG_LEVEL"
)

$lambdaVars = @{}
foreach ($key in $allowedKeys) {
    if ($rawEnv.ContainsKey($key) -and $rawEnv[$key]) {
        $lambdaVars[$key] = $rawEnv[$key]
    }
}
$lambdaVars["JIMS_STORAGE_BACKEND"] = "production"
$lambdaVars["JIMS_STRICT_PROVIDER_STARTUP"] = "true"
$lambdaVars["JIMS_AUTH_PROVIDER"] = "supabase"
$lambdaVars["JIMS_AUTH_REQUIRED"] = "true"
if ($CorsAllowOrigin) {
    $lambdaVars["CORS_ORIGINS"] = $CorsAllowOrigin
} elseif ($rawEnv.ContainsKey("CORS_ORIGINS")) {
    $lambdaVars["CORS_ORIGINS"] = $rawEnv["CORS_ORIGINS"]
}

$environmentPath = Join-Path $env:TEMP "jimsai-lambda-env.json"
@{ Variables = $lambdaVars } | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $environmentPath

aws lambda get-function --region $Region --function-name $FunctionName *> $null
if ($LASTEXITCODE -ne 0) {
    aws lambda create-function `
        --region $Region `
        --function-name $FunctionName `
        --package-type Image `
        --code ImageUri=$imageUri `
        --role $roleArn `
        --timeout 60 `
        --memory-size 2048 `
        --environment "file://$environmentPath" *> $null
} else {
    aws lambda update-function-code `
        --region $Region `
        --function-name $FunctionName `
        --image-uri $imageUri *> $null
    aws lambda wait function-updated --region $Region --function-name $FunctionName
    aws lambda update-function-configuration `
        --region $Region `
        --function-name $FunctionName `
        --timeout 60 `
        --memory-size 2048 `
        --environment "file://$environmentPath" *> $null
}

aws lambda wait function-updated --region $Region --function-name $FunctionName

$corsArg = @()
if ($lambdaVars.ContainsKey("CORS_ORIGINS") -and $lambdaVars["CORS_ORIGINS"]) {
    $origins = $lambdaVars["CORS_ORIGINS"].Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $cors = @{
        AllowOrigins = $origins
        AllowMethods = @("*")
        AllowHeaders = @("*")
        AllowCredentials = $true
        MaxAge = 300
    }
    $corsPath = Join-Path $env:TEMP "jimsai-lambda-url-cors.json"
    $cors | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $corsPath
    $corsArg = @("--cors", "file://$corsPath")
}

$functionUrl = aws lambda get-function-url-config --region $Region --function-name $FunctionName --query FunctionUrl --output text 2>$null
if ($LASTEXITCODE -ne 0 -or -not $functionUrl) {
    $functionUrl = aws lambda create-function-url-config `
        --region $Region `
        --function-name $FunctionName `
        --auth-type NONE `
        @corsArg `
        --query FunctionUrl `
        --output text
    aws lambda add-permission `
        --region $Region `
        --function-name $FunctionName `
        --statement-id FunctionURLAllowPublicAccess `
        --action lambda:InvokeFunctionUrl `
        --principal "*" `
        --function-url-auth-type NONE *> $null
} elseif ($corsArg.Count -gt 0) {
    aws lambda update-function-url-config `
        --region $Region `
        --function-name $FunctionName `
        --auth-type NONE `
        @corsArg *> $null
}

Write-Host "Lambda Function URL: $functionUrl"
Write-Host "Set Vercel NEXT_PUBLIC_API_BASE_URL=$functionUrl"
