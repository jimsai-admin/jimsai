import os
os.environ["JIMS_INTENT_EMBEDDING_TIMEOUT"] = "60"
os.environ.pop('JIMS_CLASSIFICATION_SERVICE_URL', None)
os.environ.pop('JIMS_INTENT_SERVICE_URL', None)
os.environ.pop('JIMS_RENDERER_SERVICE_URL', None)
os.environ.pop('JIMS_REASONING_SERVICE_URL', None)

from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime

compiler = SemanticCompilerRuntime()
bridge = compiler.qwen_bridge
print(f'bridge: {bridge}')
print(f'qwen_enabled: {bridge.qwen_enabled}')
print(f'local_url: {bridge.local_url}')
print(f'render_url: {bridge.render_url}')
print(f'local_api_key: {bridge.local_api_key[:10] if bridge.local_api_key else "None"}...')