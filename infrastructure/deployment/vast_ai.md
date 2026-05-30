# Vast.ai External Multimodal Encoder

JIMS-AI uses Vast.ai only as an external encoder worker. It is not a reasoning engine and it does not replace the deterministic runtime. The public API calls it through `JIMS_MULTIMODAL_ENCODER_URL`.

## 1. Build The Encoder Image

```bash
docker build -f services/multimodal-encoder/Dockerfile -t ghcr.io/YOUR_ORG/jimsai-multimodal-encoder:latest .
docker push ghcr.io/YOUR_ORG/jimsai-multimodal-encoder:latest
```

Set the pushed image in `.env`:

```text
VAST_ENCODER_IMAGE=ghcr.io/YOUR_ORG/jimsai-multimodal-encoder:latest
VAST_ENCODER_MAX_PRICE=0.40
VAST_ENCODER_MIN_GPU_RAM=16000
VAST_ENCODER_DISK_GB=50
```

## 2. Search For A GPU Offer

Use `VAST_API` or `VAST_API_KEY` from your Vast.ai account:

```bash
python scripts/vast_encoder.py search --max-price 0.40 --min-gpu-ram 16000
```

For an RTX 4000 class card, add a GPU-name filter that matches the offer name shown by Vast:

```bash
python scripts/vast_encoder.py search --gpu-name "RTX 4000 Ada" --max-price 0.40
```

## 3. Launch The Encoder

Launching spends Vast.ai credit, so the script requires `--confirm-launch`:

```bash
python scripts/vast_encoder.py launch --offer-id OFFER_ID --confirm-launch
```

The script creates a paid instance with:

```text
-p 8000:8000
-e JIMS_MULTIMODAL_ENCODER_API_KEY=...
```

After Vast assigns a public mapped port, set:

```text
JIMS_ENABLE_MULTIMODAL_ENCODERS=true
JIMS_MULTIMODAL_ENCODER_MODE=external
JIMS_MULTIMODAL_ENCODER_URL=http://VAST_HOST:MAPPED_PORT
JIMS_MULTIMODAL_ENCODER_API_KEY=<the key printed by the launch script>
```

Then verify from the API machine:

```bash
curl -H "Authorization: Bearer $JIMS_MULTIMODAL_ENCODER_API_KEY" "$JIMS_MULTIMODAL_ENCODER_URL/health"
```

## Cost Control

Your selected RTX PRO 4000 class offer at roughly `$0.21/hour` costs about `$5/day` if left running continuously. Stop or destroy the instance when not encoding media batches.
