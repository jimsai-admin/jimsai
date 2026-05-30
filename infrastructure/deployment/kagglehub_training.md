# KaggleHub Training Handoff

JIMS-AI uses KaggleHub for batch GPU training handoff. This preserves the v8 separation rule: Kaggle is used for
encoder/reranker/world-model/SPPE training artifacts, not as the runtime brain.

## Configuration

```env
KAGGLE_API_TOKEN=...
KAGGLE_DATASET_OWNER=your-kaggle-username
JIMS_MULTIMODAL_ENCODER_MODE=kaggle_batch
```

`KAGGLE_API_TOKEN` is the token from Kaggle account API settings. `KAGGLE_DATASET_OWNER` is required because
KaggleHub uploads datasets by handle, for example `username/jimsai-encoder-finetune`.

## What the UI Trigger Does

The Training UI button packages the current unified training state:

- `training_payload.json`
- generated notebook template
- dataset metadata

The orchestrator uploads that package as a private Kaggle dataset through `kagglehub.dataset_upload`.

## What It Does Not Do

KaggleHub does not currently provide the same notebook execution submission surface as the old Kaggle CLI
`kernels push` flow. Use a Kaggle GPU notebook that attaches the generated private dataset, reads
`training_payload.json`, writes artifacts, then publish/run the notebook. JIMS-AI can sync notebook outputs with
`kagglehub.notebook_output_download` when given the notebook output handle.

## Realtime Media

Kaggle batch mode is suitable for training and delayed media ingestion. It is not a low-latency encoder API.
For realtime public uploads, deploy `services/multimodal-encoder` and switch to:

```env
JIMS_MULTIMODAL_ENCODER_MODE=external
JIMS_MULTIMODAL_ENCODER_URL=https://...
```
