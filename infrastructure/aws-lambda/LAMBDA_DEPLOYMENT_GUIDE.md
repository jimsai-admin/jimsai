# JimsAI Lambda Deployment Guide

## Overview

The backend is a FastAPI app (`services/api-gateway`) deployed to AWS Lambda via a zip package.
No Docker required. The `prototype/` package is bundled with it.

**Live URLs:**
- Frontend: https://jimsai.vercel.app
- API Gateway: https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws

---

## Prerequisites

- Python 3.11+ installed locally
- AWS CLI v2 installed and configured (`aws configure`)
- AWS user `JimsAI` with Lambda, S3, and IAM permissions

Verify credentials:
```powershell
aws sts get-caller-identity
```

---

## Project Structure

```
services/api-gateway/
  app/
    lambda_handler.py   # Mangum adapter — Lambda entry point
    main.py             # FastAPI app
    routes.py           # All API routes
    config.py           # Settings
  requirements.lambda.txt  # Lean requirements (no sentence-transformers)

prototype/jimsai/       # Core runtime — bundled into the zip
```

**Lambda entry point:** `app.lambda_handler.handler`

---

## Lambda-Specific Fixes

The following files were patched to work on Lambda's read-only filesystem:

| File | Fix |
|------|-----|
| `prototype/jimsai/kaggle_orchestrator.py` | Uses `/tmp/.kaggle_runs` on Lambda |
| `prototype/jimsai/event_store.py` | Uses `/tmp/.logs` on Lambda |
| `prototype/jimsai/semantic_compiler.py` | Falls back to `_FallbackClassifier` when `sentence-transformers` not installed |

Detection: `os.getenv("AWS_LAMBDA_FUNCTION_NAME")` — automatically set by AWS, no manual config needed.

---

## Build

Run from the repo root `C:\Users\ajibe\Jims-AI`:

```powershell
# 1. Clean previous build
Remove-Item -Recurse -Force ".lambda-build" -ErrorAction SilentlyContinue
Remove-Item -Force "lambda-package.zip" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path ".lambda-build" | Out-Null

# 2. Install dependencies for Linux (Lambda runtime)
pip install `
  --target ".lambda-build" `
  --platform manylinux2014_x86_64 `
  --implementation cp `
  --python-version 3.11 `
  --only-binary=:all: `
  --upgrade `
  -r "services\api-gateway\requirements.lambda.txt"

# 3. Copy app and prototype
Copy-Item -Recurse -Force "services\api-gateway\app" ".lambda-build\app"
Copy-Item -Recurse -Force "prototype" ".lambda-build\prototype"

# 4. Zip
Compress-Archive -Path ".lambda-build\*" -DestinationPath "lambda-package.zip"

$size = [math]::Round((Get-Item "lambda-package.zip").Length / 1MB, 1)
Write-Host "Package size: $size MB"
# Expected: ~55MB. Must be under 250MB.
```

---

## Upload

The zip exceeds the 69MB direct upload limit, so we upload via S3:

```powershell
# Upload zip to S3
aws s3 cp "lambda-package.zip" s3://jimsai-lambda-deploy-095931689519/lambda-package.zip

# Deploy to Lambda
aws lambda update-function-code `
  --function-name jimsai-api-gateway `
  --s3-bucket jimsai-lambda-deploy-095931689519 `
  --s3-key lambda-package.zip `
  --region us-east-1 | Out-Null

# Wait for update to complete
aws lambda wait function-updated `
  --function-name jimsai-api-gateway `
  --region us-east-1

Write-Host "Deploy complete"
```

---

## Test

### Direct invocation (no HTTP, bypasses auth):
```powershell
# Save test payload
@'
{"version":"2.0","routeKey":"GET /health","rawPath":"/health","rawQueryString":"","headers":{"host":"localhost"},"requestContext":{"http":{"method":"GET","path":"/health","sourceIp":"127.0.0.1","userAgent":"test"},"accountId":"095931689519","stage":"$default"},"isBase64Encoded":false}
'@ | Set-Content "$env:TEMP\lambda-payload.json"

# Invoke
aws lambda invoke `
  --function-name jimsai-api-gateway `
  --region us-east-1 `
  --cli-binary-format raw-in-base64-out `
  --payload "file://$env:TEMP\lambda-payload.json" `
  "$env:TEMP\response.json"

Get-Content "$env:TEMP\response.json"
# Expected: {"statusCode":200,"body":"{\"status\":\"ok\"...}"}
```

### Public URL test:
```powershell
Invoke-RestMethod -Uri "https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws/health"
# Expected: status=ok, service=api-gateway, deterministic=True
```

### Auth endpoint test:
```powershell
Invoke-RestMethod -Uri "https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws/v1/auth/config"
```

---

## Update Environment Variables

If you change `.env` values and need to push them to Lambda:

```powershell
$allowedKeys = @(
    "JIMS_STORAGE_BACKEND","JIMS_STRICT_PROVIDER_STARTUP","JIMS_AUTH_PROVIDER",
    "JIMS_AUTH_REQUIRED","JIMS_SUPABASE_DEFAULT_SCOPES","JIMS_GRAPH_PROVIDER",
    "JIMS_ENABLE_NEO4J","JIMS_ENABLE_GROQ_T1","JIMS_ENABLE_GROQ_T2",
    "JIMS_ENABLE_GROQ_CANVAS","JIMS_ENABLE_GROQ_INVENTION",
    "JIMS_ADAPTIVE_TRANSFORMER_THINNING","SUPABASE_URL","SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY","NEO4J_URI","NEO4J_USER","NEO4J_PASSWORD","NEO4J_DATABASE",
    "REDIS_URL","CF_ACCOUNT_ID","CF_R2_BUCKET","CF_R2_ACCESS_KEY","CF_R2_SECRET_KEY",
    "CF_VECTORIZE_INDEX","CF_VECTORIZE_API_TOKEN","CF_VECTORIZE_DIMENSIONS",
    "GROQ_API_KEY","LOG_LEVEL","CORS_ORIGINS"
)

$rawEnv = @{}
Get-Content ".env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value) { $rawEnv[$key] = $value }
    }
}

$envVars = @{}
foreach ($key in $allowedKeys) {
    if ($rawEnv.ContainsKey($key)) { $envVars[$key] = $rawEnv[$key] }
}
$envVars["CORS_ORIGINS"] = "https://jimsai.vercel.app"
$envVars["JIMS_STORAGE_BACKEND"] = "production"
$envVars["JIMS_AUTH_REQUIRED"] = "true"
$envVars["JIMS_AUTH_PROVIDER"] = "supabase"

$envJson = @{ Variables = $envVars } | ConvertTo-Json -Depth 5
$envJson | Set-Content "$env:TEMP\jimsai-lambda-env.json"

aws lambda update-function-configuration `
  --function-name jimsai-api-gateway `
  --region us-east-1 `
  --environment "file://$env:TEMP\jimsai-lambda-env.json"
```

---

## Full Redeploy (one command)

Copy this whole block to redeploy after any code change:

```powershell
cd C:\Users\ajibe\Jims-AI

Remove-Item -Recurse -Force ".lambda-build" -ErrorAction SilentlyContinue
Remove-Item -Force "lambda-package.zip" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path ".lambda-build" | Out-Null

pip install --target ".lambda-build" --platform manylinux2014_x86_64 --implementation cp --python-version 3.11 --only-binary=:all: --upgrade -r "services\api-gateway\requirements.lambda.txt"

Copy-Item -Recurse -Force "services\api-gateway\app" ".lambda-build\app"
Copy-Item -Recurse -Force "prototype" ".lambda-build\prototype"
Compress-Archive -Path ".lambda-build\*" -DestinationPath "lambda-package.zip"

aws s3 cp "lambda-package.zip" s3://jimsai-lambda-deploy-095931689519/lambda-package.zip
aws lambda update-function-code --function-name jimsai-api-gateway --s3-bucket jimsai-lambda-deploy-095931689519 --s3-key lambda-package.zip --region us-east-1 | Out-Null
aws lambda wait function-updated --function-name jimsai-api-gateway --region us-east-1

Write-Host "Deploy complete - testing..."
Invoke-RestMethod -Uri "https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws/health"
```

---

## CloudWatch Logs

View Lambda logs in real time:

```powershell
aws logs tail /aws/lambda/jimsai-api-gateway --follow --region us-east-1
```

Or in the AWS Console:
1. Go to Lambda → jimsai-api-gateway → Monitor tab
2. Click **"View CloudWatch logs"**


---

## What NOT to Commit

Add to `.gitignore` if not already there:

```
.lambda-build/
lambda-package.zip
.env
.logs/
.kaggle_runs/
.cache/
```
