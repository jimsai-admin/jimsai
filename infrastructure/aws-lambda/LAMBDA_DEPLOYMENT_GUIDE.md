# Lambda Deployment Notes

The complete production deployment guide now lives at:

```text
DEPLOYMENT_GUIDE.md
```

Use this script for Lambda code deployment:

```powershell
cd C:\Users\ajibe\Jims-AI
.\infrastructure\aws-lambda\deploy-lambda-zip.ps1
```

Current Lambda entry point:

```text
app.lambda_handler.handler
```

Current Lambda package source:

```text
services/api-gateway/app
prototype/jimsai
services/api-gateway/requirements.lambda.txt
```

Do not put `sentence-transformers`, PyTorch, or GGUF inference into Lambda. Lambda calls the Hugging Face Space for embeddings, capability classification, and bounded local Qwen interfaces.
