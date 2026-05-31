#!/usr/bin/env python3
"""Pre-download the multilingual embedding model."""
import sys
print("Downloading intfloat/multilingual-e5-small model...")
try:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("intfloat/multilingual-e5-small", cache_folder=".cache/models")
    print("✅ Model downloaded and cached successfully")
    # Test it works
    embeddings = model.encode(["test"])
    print(f"✅ Model loaded: {embeddings.shape}")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
