import py_compile, sys

files = [
    "prototype/jimsai/semantic_compiler.py",
    "prototype/jimsai/runtime_layers.py",
    "prototype/jimsai/retrieval.py",
    "prototype/jimsai/pipeline.py",
    "prototype/jimsai/capability_router.py",
    "prototype/jimsai/ingestion_worker_pool.py",
    "prototype/jimsai/intent_classifier.py",
    "prototype/jimsai/execution_runtime.py",
]
ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"OK  {f}")
    except py_compile.PyCompileError as e:
        print(f"ERR {f}: {e}")
        ok = False
sys.exit(0 if ok else 1)
