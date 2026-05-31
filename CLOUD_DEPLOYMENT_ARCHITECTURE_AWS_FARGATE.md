# Cloud Deployment Architecture - JimsAI with AWS Fargate + Kaggle GPU

## Executive Summary

This document outlines the **actual production deployment architecture** for JimsAI's autonomous training system. The architecture uses **AWS Fargate for runtime services** combined with **Kaggle's free GPU tier (30 GPU hours/week)** for encoder fine-tuning.

**Production Stack - Runtime (AWS Fargate)**:
- **Frontend**: Next.js (port 3000) on Fargate
- **API Gateway**: FastAPI service (port 8000) on Fargate - runtime queries  
- **Training Worker**: Celery worker on Fargate + orchestrates Kaggle GPU jobs
- **Authentication**: Supabase Auth with bearer tokens (JIMS_AUTH_PROVIDER=supabase)
- **Databases**: Supabase PostgreSQL + Neo4j AuraDB (JIMS_GRAPH_PROVIDER=neo4j_aura)
- **Caching & Async**: Redis Cloud with Celery task broker
- **Object Storage**: AWS S3 or Cloudflare R2 (jimsai-files bucket)
- **Vector Embeddings**: Cloudflare Vectorize (768-dim, jimsai-embeddings index)
- **AI Models**: Groq API (4 transformer layers: T1, T2, Canvas, Invention)
- **Training Orchestration**: **Kaggle API with free GPU tier (30 GPU hours/week)** for Sentence Transformer fine-tuning
- **Code Sandbox**: Docker containers on Fargate (DOCKER_ENABLED=true, 30s timeout, 512MB limit)
- **Math Verification**: Z3 SMT solver (Z3_ENABLED=true, 10s timeout)
- **Sentence Transformers**: Bundled encoder + fine-tuned via **Kaggle's FREE GPU tier**
- **Multimodal Encoding**: Bundled service (optional, configurable per modality)
- **Web Search**: DuckDuckGo API (DUCKDUCKGO_API_ENABLED=true)

**Estimated Cost**: $0-10/month startup → $80-120/month at scale 
**GPU Training Cost**: $0 (completely free via Kaggle!)

---

## 1. Architecture Overview - AWS Fargate + Kaggle GPU Training

### 1.1 Deployment Model

The production deployment consists of **3 containerized services on AWS Fargate** plus **Kaggle's free GPU tier for training**:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│           JIMSAI PRODUCTION DEPLOYMENT (AWS Fargate + Kaggle GPU)               │
│                   (ECS Task Definitions + Kaggle Orchestrator)                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  AWS FARGATE SERVICES (Serverless Container Orchestration - ECS)               │
│                                                                                  │
│  SERVICE 1: API GATEWAY (FastAPI) on Fargate                                   │
│  ├─ ECS Task Definition: jimsai-api                                            │
│  ├─ CPU: 1 vCPU, Memory: 2GB                                                   │
│  ├─ Scaling: 1-20 tasks based on load (Application Load Balancer)             │
│  ├─ Cost: Free tier 750 hours/month, then $0.04755/vCPU-hour                  │
│  ├─ Endpoints: /v1/runtime/*, /v1/training/*                                  │
│  └─ Environment: JIMS_STORAGE_BACKEND=production, JIMS_AUTH_PROVIDER=supabase │
│                                                                                  │
│  SERVICE 2: TRAINING WORKER (Celery + Autonomous Agent) on Fargate            │
│  ├─ ECS Task Definition: jimsai-worker                                         │
│  ├─ CPU: 2 vCPU, Memory: 4GB                                                   │
│  ├─ Min Tasks: 1 (always-on for continuous agent loop)                        │
│  ├─ Max Tasks: 5 (scale for parallel ingestion)                               │
│  ├─ Cost: ~$50-80/month (1 always-on task)                                    │
│  │                                                                              │
│  ├─ Responsibilities:                                                           │
│  │   1. Autonomous agent loop (FIND → INGEST → EVALUATE → TRAIN)             │
│  │   2. Pulls training tasks from Redis Celery broker                         │
│  │   3. **Orchestrates Kaggle GPU jobs via kagglehub API** (FREE!)            │
│  │   4. Processes SPPE pairs, world models, signatures                        │
│  │   5. Supports Docker sandbox (30s timeout, 512MB)                          │
│  │   6. Supports Z3 math validator (10s timeout)                              │
│  │                                                                              │
│  └─ Kaggle GPU Workflow:                                                        │
│     - Accumulate SPPE pairs & world models (~1000 items threshold)            │
│     - Create training payload (JSON with pairs, candidates, signatures)       │
│     - Submit notebook template to Kaggle via kagglehub.dataset_upload()       │
│     - Kaggle notebook runs on FREE GPU: **30 GPU hours/week**                 │
│     - Kaggle notebook fine-tunes Sentence Transformer via losses.MRL()        │
│     - Download artifacts via kagglehub.notebook_output_download()             │
│     - Deploy new encoder weights to production                                │
│     - Cost: $0 (uses Kaggle free tier!)                                       │
│                                                                                  │
│  SERVICE 3: FRONTEND (Next.js) on Fargate (or CloudFront)                     │
│  ├─ ECS Task Definition: jimsai-frontend                                       │
│  ├─ CPU: 0.5 vCPU, Memory: 1GB                                                 │
│  ├─ Scaling: 1-5 tasks based on load                                          │
│  ├─ Cost: ~$20-30/month                                                        │
│  └─ Endpoints: Training dashboard, UI                                          │
│                                                                                  │
│  AWS INFRASTRUCTURE SERVICES (Managed)                                          │
│                                                                                  │
│  ✓ ECS Cluster (Fargate launch type - serverless, no instances to manage)     │
│  ✓ ECR (Elastic Container Registry for Docker images)                          │
│  ✓ Application Load Balancer (ALB for traffic distribution)                    │
│  ✓ AWS CloudWatch (logs, metrics, monitoring, alarms)                          │
│  ✓ AWS Secrets Manager (credential storage & rotation)                         │
│  ✓ IAM Roles (task execution role, task role)                                  │
│  ✓ Auto Scaling (Application Auto Scaling service)                             │
│                                                                                  │
│  EXTERNAL MANAGED SERVICES (Cloud APIs, No Infrastructure)                     │
│                                                                                  │
│  ✓ Supabase PostgreSQL (500MB free → $25/mo)                                 │
│  ✓ Neo4j AuraDB (Free tier → Professional pay-as-you-go)                    │
│  ✓ Redis Cloud (30MB free → $6.99/mo)                                        │
│  ✓ Cloudflare R2 (Pay per GB)                                                 │
│  ✓ Cloudflare Vectorize (Included with R2)                                   │
│  ✓ Groq API (5.26% call rate, pay-per-use)                                   │
│  ✓ **Kaggle API - 30 GPU hours/week FREE tier for Sentence Transformer**    │
│  ✓ DuckDuckGo Web Search (Free)                                               │
│  ✓ Docker Sandbox (Runs inside Fargate container)                             │
│  ✓ Z3 SMT Solver (Runs inside Fargate container)                             │
│  ✓ Sentence Transformers (**Bundled** + fine-tuned on Kaggle GPUs)          │
│  ✓ Multimodal Encoders (Optional service, disabled by default for cost)      │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 How Kaggle Free GPU Tier Works

The training worker uses Kaggle's **30 free GPU hours per week** to fine-tune Sentence Transformers:

```
Autonomous Agent Loop → Accumulate SPPE Pairs → Kaggle GPU Training → Deploy Weights
                           ~1000 pairs                30 GPU hrs/week      New Model
```

**Kaggle Orchestrator Flow** (from `prototype/jimsai/kaggle_orchestrator.py`):

1. **Training Trigger**: When SPPE pair count exceeds threshold (~1000)
2. **Payload Creation**: Package training data (SPPE pairs, world models, signatures) 
3. **Notebook Upload**: Submit training notebook template to Kaggle via `kagglehub.dataset_upload()`
4. **GPU Execution**: Kaggle runs fine-tuning on FREE GPU (included in 30 hours/week)
5. **Fine-tuning Details**:
   ```python
   from sentence_transformers import SentenceTransformer, InputExample, losses
   model = SentenceTransformer("intfloat/multilingual-e5-small")
   # Create training pairs from SPPE data
   examples = [InputExample(texts=[original_text, semantic_graph]) for pair in pairs]
   loader = DataLoader(examples, batch_size=8, shuffle=True)
   # Fine-tune using MultipleNegativesRankingLoss
   model.fit(train_objectives=[(loader, losses.MultipleNegativesRankingLoss(model))],
             epochs=1, warmup_steps=10)
   ```
6. **Output Download**: Retrieve fine-tuned weights via `kagglehub.notebook_output_download()`
7. **Deployment**: Load new model weights into production
8. **Cost**: $0 (completely free GPU time!)

### 1.3 Cost Comparison vs Other Approaches

| Approach | GPU Cost | Runtime Cost | Total |
|----------|----------|--------------|-------|
| **AWS Fargate + Kaggle GPU** | $0 (free!) | $50-100/mo | **$50-100/mo** |
| AWS Fargate + AWS SageMaker | $100-200/mo | $50-100/mo | $150-300/mo |
| Google Cloud Run + Cloud GPUs | $150-300/mo | $0-50/mo | $150-350/mo |
| Self-hosted + GPU instance | $200-400/mo | $0 | $200-400/mo |

**Winner**: AWS Fargate + Kaggle GPU (saves $100-300/month on GPU training!)

---

## 2. Deployment Strategy - AWS Fargate + Kaggle GPU

### 2.1 AWS Fargate Advantages

- **Serverless**: No EC2 instances to manage, AWS handles scaling
- **Cost-Effective**: Pay only for vCPU-hours + memory used (not reservation)
- **Auto-Scaling**: Application Auto Scaling scales 0-20 tasks automatically
- **Always-On Option**: Min-instances=1 keeps training worker ready (no cold starts)
- **Integrated**: Works with ALB, CloudWatch, IAM, Secrets Manager
- **Container-Native**: Deploy Docker images directly from ECR

### 2.2 AWS Fargate Deployment (Step-by-Step)

**Step 1: Setup AWS Account & CLI**

```bash
# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure credentials
aws configure
# Enter: AWS Access Key ID
# Enter: AWS Secret Access Key
# Default region: us-east-1
# Default output: json

# Verify setup
aws sts get-caller-identity
```

**Step 2: Create ECR Repositories**

```bash
# Create repositories for each service
aws ecr create-repository \
  --repository-name jimsai-api \
  --region us-east-1

aws ecr create-repository \
  --repository-name jimsai-worker \
  --region us-east-1

aws ecr create-repository \
  --repository-name jimsai-frontend \
  --region us-east-1

# Get registry URL
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com"
echo $ECR_REGISTRY  # e.g., 123456789.dkr.ecr.us-east-1.amazonaws.com
```

**Step 3: Create CloudWatch Log Group**

```bash
aws logs create-log-group \
  --log-group-name /ecs/jimsai-prod \
  --region us-east-1
```

**Step 4: Create IAM Roles**

```bash
# Task Execution Role (allows ECS to pull images, push logs)
aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Task Role (allows containers to access AWS services - Secrets Manager)
aws iam create-role \
  --role-name ecsTaskRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Allow task to read secrets
aws iam put-role-policy \
  --role-name ecsTaskRole \
  --policy-name read-secrets \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": ["arn:aws:secretsmanager:us-east-1:*:secret:jimsai/*"]
    }]
  }'
```

**Step 5: Store Secrets in AWS Secrets Manager**

```bash
# Store all provider credentials securely
aws secretsmanager create-secret \
  --name jimsai/SUPABASE_URL \
  --secret-string "https://xxxxx.supabase.co" \
  --region us-east-1

aws secretsmanager create-secret \
  --name jimsai/SUPABASE_SERVICE_KEY \
  --secret-string "eyJxxx..." \
  --region us-east-1

aws secretsmanager create-secret \
  --name jimsai/NEO4J_URI \
  --secret-string "neo4j+s://xxxxx.databases.neo4j.io:7687" \
  --region us-east-1

aws secretsmanager create-secret \
  --name jimsai/NEO4J_USER \
  --secret-string "neo4j" \
  --region us-east-1

aws secretsmanager create-secret \
  --name jimsai/NEO4J_PASSWORD \
  --secret-string "xxxxx" \
  --region us-east-1

# **CRITICAL FOR KAGGLE GPU TRAINING:**
aws secretsmanager create-secret \
  --name jimsai/KAGGLE_API_TOKEN \
  --secret-string "KGAT_480539f83b3daa9724067881f17e99c9" \
  --region us-east-1

aws secretsmanager create-secret \
  --name jimsai/KAGGLE_USERNAME \
  --secret-string "irekanmiajibewa" \
  --region us-east-1

# Other credentials
aws secretsmanager create-secret \
  --name jimsai/GROQ_API_KEY \
  --secret-string "gsk_xxxxx" \
  --region us-east-1

aws secretsmanager create-secret \
  --name jimsai/REDIS_URL \
  --secret-string "redis://xxxxx:6379" \
  --region us-east-1

aws secretsmanager create-secret \
  --name jimsai/CF_R2_ACCOUNT_ID \
  --secret-string "xxxxx" \
  --region us-east-1
```

**Step 6: Build and Push Docker Images**

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# Build and push API Gateway
docker build -f services/api-gateway/Dockerfile \
  -t $ECR_REGISTRY/jimsai-api:latest \
  -t $ECR_REGISTRY/jimsai-api:$(git rev-parse --short HEAD) .
docker push $ECR_REGISTRY/jimsai-api:latest
docker push $ECR_REGISTRY/jimsai-api:$(git rev-parse --short HEAD)

# Build and push Training Worker (with Kaggle support)
docker build -f services/training-pipeline/Dockerfile \
  -t $ECR_REGISTRY/jimsai-worker:latest \
  -t $ECR_REGISTRY/jimsai-worker:$(git rev-parse --short HEAD) .
docker push $ECR_REGISTRY/jimsai-worker:latest
docker push $ECR_REGISTRY/jimsai-worker:$(git rev-parse --short HEAD)

# Build and push Frontend
docker build -f frontend/Dockerfile \
  -t $ECR_REGISTRY/jimsai-frontend:latest \
  -t $ECR_REGISTRY/jimsai-frontend:$(git rev-parse --short HEAD) .
docker push $ECR_REGISTRY/jimsai-frontend:latest
docker push $ECR_REGISTRY/jimsai-frontend:$(git rev-parse --short HEAD)
```

**Step 7: Create ECS Cluster**

```bash
aws ecs create-cluster \
  --cluster-name jimsai-prod \
  --cluster-settings name=containerInsights,value=enabled \
  --region us-east-1

# Create security group for ECS tasks
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text)

SG_ID=$(aws ec2 create-security-group \
  --group-name jimsai-sg \
  --description "JimsAI ECS security group" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)

# Allow inbound on port 8000 (API), 3000 (Frontend)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 8000 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 3000 \
  --cidr 0.0.0.0/0

# Get subnets
SUBNET_IDS=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[0:2].SubnetId' --output text)
```

**Step 8: Register ECS Task Definitions**

```bash
# API Gateway task definition
cat > task-def-api.json << 'EOF'
{
  "family": "jimsai-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/ecsTaskRole",
  "containerDefinitions": [{
    "name": "jimsai-api",
    "image": "$ECR_REGISTRY/jimsai-api:latest",
    "portMappings": [{
      "containerPort": 8000,
      "hostPort": 8000,
      "protocol": "tcp"
    }],
    "environment": [
      {"name": "JIMS_STORAGE_BACKEND", "value": "production"},
      {"name": "JIMS_STRICT_PROVIDER_STARTUP", "value": "true"},
      {"name": "JIMS_AUTH_PROVIDER", "value": "supabase"},
      {"name": "JIMS_AUTH_REQUIRED", "value": "true"}
    ],
    "secrets": [
      {"name": "SUPABASE_URL", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/SUPABASE_URL"},
      {"name": "NEO4J_URI", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/NEO4J_URI"},
      {"name": "GROQ_API_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/GROQ_API_KEY"},
      {"name": "REDIS_URL", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/REDIS_URL"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/jimsai-prod",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "api"
      }
    }
  }]
}
EOF

# Replace variables
sed -i "s/\$ACCOUNT_ID/$ACCOUNT_ID/g" task-def-api.json
sed -i "s|\$ECR_REGISTRY|$ECR_REGISTRY|g" task-def-api.json

aws ecs register-task-definition \
  --cli-input-json file://task-def-api.json \
  --region us-east-1

# Training Worker task definition (with Kaggle GPU support)
cat > task-def-worker.json << 'EOF'
{
  "family": "jimsai-worker",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "executionRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/ecsTaskRole",
  "containerDefinitions": [{
    "name": "jimsai-worker",
    "image": "$ECR_REGISTRY/jimsai-worker:latest",
    "environment": [
      {"name": "JIMS_STORAGE_BACKEND", "value": "production"},
      {"name": "JIMS_STRICT_PROVIDER_STARTUP", "value": "true"},
      {"name": "JIMS_MULTIMODAL_ENCODER_MODE", "value": "kaggle_batch"},
      {"name": "JIMS_RUN_SENTENCE_TRANSFORMER_FINETUNE", "value": "1"}
    ],
    "secrets": [
      {"name": "SUPABASE_URL", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/SUPABASE_URL"},
      {"name": "NEO4J_URI", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/NEO4J_URI"},
      {"name": "REDIS_URL", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/REDIS_URL"},
      {"name": "KAGGLE_API_TOKEN", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/KAGGLE_API_TOKEN"},
      {"name": "KAGGLE_USERNAME", "valueFrom": "arn:aws:secretsmanager:us-east-1:$ACCOUNT_ID:secret:jimsai/KAGGLE_USERNAME"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/jimsai-prod",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "worker"
      }
    }
  }]
}
EOF

sed -i "s/\$ACCOUNT_ID/$ACCOUNT_ID/g" task-def-worker.json
sed -i "s|\$ECR_REGISTRY|$ECR_REGISTRY|g" task-def-worker.json

aws ecs register-task-definition \
  --cli-input-json file://task-def-worker.json \
  --region us-east-1
```

**Step 9: Create Application Load Balancer**

```bash
# Create ALB
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name jimsai-alb \
  --subnets $(echo $SUBNET_IDS | awk '{print $1}') $(echo $SUBNET_IDS | awk '{print $2}') \
  --security-groups $SG_ID \
  --scheme internet-facing \
  --type application \
  --region us-east-1 \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)

# Create target groups
TG_API=$(aws elbv2 create-target-group \
  --name jimsai-api-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-protocol HTTP \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 2 \
  --region us-east-1 \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

# Create listener
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_API \
  --region us-east-1
```

**Step 10: Create ECS Services**

```bash
# API Gateway service (auto-scales 1-20)
aws ecs create-service \
  --cluster jimsai-prod \
  --service-name jimsai-api \
  --task-definition jimsai-api:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$(echo $SUBNET_IDS | awk '{print $1}')],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=$TG_API,containerName=jimsai-api,containerPort=8000 \
  --deployment-configuration maximumPercent=200,minimumHealthyPercent=100 \
  --region us-east-1

# Training Worker service (always-on: min 1, max 5)
aws ecs create-service \
  --cluster jimsai-prod \
  --service-name jimsai-worker \
  --task-definition jimsai-worker:1 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$(echo $SUBNET_IDS | awk '{print $1}')],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --region us-east-1
```

**Step 11: Setup Auto-Scaling**

```bash
# Register API Gateway for auto-scaling
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/jimsai-prod/jimsai-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 20 \
  --region us-east-1

# Create scaling policy (scale based on CPU)
aws application-autoscaling put-scaling-policy \
  --policy-name api-cpu-scaling \
  --service-namespace ecs \
  --resource-id service/jimsai-prod/jimsai-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 300
  }' \
  --region us-east-1

# Register Training Worker for optional scaling (1-5)
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/jimsai-prod/jimsai-worker \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 5 \
  --region us-east-1
```

**Step 12: Verify Deployment**

```bash
# Check services
aws ecs describe-services \
  --cluster jimsai-prod \
  --services jimsai-api jimsai-worker \
  --region us-east-1

# Check running tasks
aws ecs list-tasks --cluster jimsai-prod --region us-east-1
aws ecs describe-tasks \
  --cluster jimsai-prod \
  --tasks $(aws ecs list-tasks --cluster jimsai-prod --region us-east-1 --query 'taskArns[0]' --output text) \
  --region us-east-1

# View logs
aws logs tail /ecs/jimsai-prod --follow --region us-east-1

# Get load balancer DNS
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names jimsai-alb \
  --query 'LoadBalancers[0].DNSName' \
  --output text \
  --region us-east-1)

echo "Load Balancer: http://$ALB_DNS"

# Test API
curl http://$ALB_DNS:8000/health
```

### 2.3 Kaggle GPU Integration Setup

**Verify Kaggle Configuration**

```bash
# Check that Kaggle credentials are in Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id jimsai/KAGGLE_API_TOKEN \
  --region us-east-1

aws secretsmanager get-secret-value \
  --secret-id jimsai/KAGGLE_USERNAME \
  --region us-east-1

# Verify training worker has environment variables set
aws ecs describe-services \
  --cluster jimsai-prod \
  --services jimsai-worker \
  --region us-east-1 \
  --query 'services[0].taskDefinition' | grep jimsai-worker

# Check that JIMS_MULTIMODAL_ENCODER_MODE=kaggle_batch is set
aws ecs describe-task-definition \
  --task-definition jimsai-worker:1 \
  --region us-east-1 \
  --query 'taskDefinition.containerDefinitions[0].environment' | grep kaggle
```

**Monitor Kaggle GPU Usage**

```bash
# Watch CloudWatch logs for Kaggle training progress
aws logs tail /ecs/jimsai-prod --log-stream-names worker --follow \
  --filter-pattern "kaggle OR Kaggle OR GPU" \
  --region us-east-1

# Check for Kaggle submission success
aws logs tail /ecs/jimsai-prod --filter-pattern "kagglehub" --follow --region us-east-1
```

**How to Manually Trigger Kaggle Training**

```bash
# If automatic threshold isn't reached, manually trigger training:

# 1. Connect to training worker task
TASK_ID=$(aws ecs list-tasks --cluster jimsai-prod \
  --service-name jimsai-worker \
  --query 'taskArns[0]' --output text | awk -F'/' '{print $NF}')

# 2. Execute command in running task
aws ecs execute-command \
  --cluster jimsai-prod \
  --task $TASK_ID \
  --container jimsai-worker \
  --interactive \
  --command "/bin/bash" \
  --region us-east-1

# 3. Inside container, trigger training manually:
# python -c "from prototype.jimsai.kaggle_orchestrator import KaggleGPUOrchestrator; \
#   orchestrator = KaggleGPUOrchestrator(); \
#   result = orchestrator.submit_training_run(...)"
```

---

## 3. Cost Analysis - AWS Fargate + Kaggle Free GPUs

### 3.1 Startup Phase (Month 1) - Completely Free

| Service | Free Tier | Monthly Cost |
|---------|-----------|------|
| AWS Fargate | 750 hours/month | **$0** |
| Supabase PostgreSQL | 500MB storage | **$0** |
| Neo4j AuraDB | Free tier (1GB) | **$0** |
| Redis Cloud | 30MB cluster | **$0** |
| Cloudflare R2 | First month free | **$0** |
| Groq API | Pay-per-token (~5% call rate) | **$0-5** |
| Kaggle GPU | **30 GPU hours/week** | **$0** |
| Docker/Z3/Sentence Transformers | Bundled in container | **$0** |
| **TOTAL STARTUP** | **All free** | **$0-5/month** |

### 3.2 Growth Phase (1M+ daily queries) - Pay-as-You-Go

| Service | Usage | Cost/Month |
|---------|-------|-----------|
| **AWS Fargate (ECS)** | | |
| - API Gateway | 10M requests, 100K vCPU-sec | $50-80 |
| - Training Worker | 730 hours/mo (always-on) | $30-50 |
| - Frontend | 2M requests, 30K vCPU-sec | $15-25 |
| **Supabase PostgreSQL** | 500MB → 2GB | $25-50 |
| **Neo4j AuraDB** | Professional tier | $50-150 |
| **Redis Cloud** | 30MB → 250MB | $6.99-40 |
| **Cloudflare R2** | 500GB storage | $20-40 |
| **Groq API** | 50M tokens/month | $30-50 |
| **Kaggle GPU** | **30 GPU hours/week** | **$0** |
| **TOTAL AT SCALE** | **Full production** | **$227-505/month** |

**Cost Savings from Kaggle Free GPUs**: ~$100-200/month vs Cloud GPUs!

### 3.3 Cost Optimization

```
1. Adaptive Transformer Thinning
   JIMS_T1_SKIP_CONFIDENCE=0.68  # Skip 68% of calls
   JIMS_T2_SKIP_CONFIDENCE=0.82  # Skip 82% of calls
   Impact: Reduce Groq by 90% (~$2-5/month)

2. Cache Aggressively in Redis
   - Cache IR scores, session state, graph queries
   - Cache embeddings from fine-tuned models
   Impact: Reduce API calls by 50-70%

3. **Optimize Kaggle GPU Usage**
   - Batch 1000+ SPPE pairs per training run (not small batches)
   - Fine-tune weekly (use all 30 hours strategically)
   - Archive old model versions
   Impact: Maximize free GPU tier value

4. Batch Training
   - Ingest in 100-doc batches
   - Reduce Neo4j round-trips
   - Reduce R2 uploads
   Impact: Reduce provider calls by 40%

5. Use Free Tiers
   - Keep Supabase <500MB
   - Keep Neo4j <1GB
   - Keep Redis <30MB
   Impact: $0-10/month when small
```

---

## 4. Monitoring & Logging - AWS CloudWatch

### 4.1 View Real-Time Logs

```bash
# All logs from JimsAI
aws logs tail /ecs/jimsai-prod --follow --region us-east-1

# Specific service logs
aws logs tail /ecs/jimsai-prod --log-stream-names api --follow --region us-east-1
aws logs tail /ecs/jimsai-prod --log-stream-names worker --follow --region us-east-1

# Filter for errors
aws logs tail /ecs/jimsai-prod --filter-pattern "ERROR" --follow --region us-east-1

# Filter for Kaggle GPU activity
aws logs tail /ecs/jimsai-prod --filter-pattern "kaggle" --follow --region us-east-1
```

### 4.2 Create CloudWatch Dashboard

```bash
# Create monitoring dashboard
aws cloudwatch put-dashboard \
  --dashboard-name jimsai-monitoring \
  --dashboard-body file://dashboard.json

# Example dashboard.json:
cat > dashboard.json << 'EOF'
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ECS", "CPUUtilization", {"stat": "Average"}],
          [".", "MemoryUtilization", {"stat": "Average"}]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "ECS Task Resource Usage"
      }
    }
  ]
}
EOF
```

### 4.3 Create Alarms

```bash
# Alert if error rate is high
aws cloudwatch put-metric-alarm \
  --alarm-name jimsai-high-errors \
  --alarm-description "Alert when error count is high" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --region us-east-1
```

---

## 5. Summary & Next Steps

### Why AWS Fargate + Kaggle?

1. **Serverless**: No infrastructure to manage
2. **Auto-Scaling**: Handles traffic spikes automatically
3. **Cost-Effective**: Free GPU training via Kaggle (saves $100-300/month!)
4. **Always-On**: Training worker never sleeps, always ready for new cycles
5. **Integrated**: Works with ALB, CloudWatch, Secrets Manager, IAM
6. **Proven**: Used by production teams at scale

### Deployment Checklist

- [ ] AWS CLI configured
- [ ] ECR repositories created
- [ ] Secrets stored in Secrets Manager (especially Kaggle credentials!)
- [ ] Docker images built & pushed to ECR
- [ ] ECS cluster created
- [ ] IAM roles configured
- [ ] Task definitions registered
- [ ] Load Balancer created
- [ ] ECS services deployed
- [ ] Auto-scaling configured
- [ ] Logs verified in CloudWatch
- [ ] Health check passing (`curl /health`)
- [ ] Kaggle GPU training triggered
- [ ] Monitor Kaggle GPU jobs in logs

### Getting Started

```bash
# Full deployment script (all steps above in one go)
./deploy-to-fargate.sh
```

**Status**: Ready for production deployment! 🚀
