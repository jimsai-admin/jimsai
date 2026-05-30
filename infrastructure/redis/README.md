# Redis

Session state, IR hot cache, graph shortcut cache, ontology staging, and Celery broker/result storage for canvas
and invention jobs.

Set `REDIS_URL` and enable `JIMS_STORAGE_BACKEND=production` or `JIMS_ENABLE_CELERY=true`. Workers start with:

```bash
celery -A prototype.jimsai.celery_runtime:celery_app worker --loglevel=INFO
```
