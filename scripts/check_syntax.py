import py_compile, sys

files = [
    "prototype/jimsai/semantic_compiler.py",
    "prototype/jimsai/runtime_layers.py",
    "prototype/jimsai/retrieval.py",
    "prototype/jimsai/pipeline.py",
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
