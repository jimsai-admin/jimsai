# Fix _strip_think function in modal reasoning service
import re

with open('C:/Users/ajibe/Jims-AI/modal/modal_reasoning_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

pattern = r'(def _strip_think\(text: str\) -> str:\n\s*return re\.sub\(r".*?".*?\.strip\(\))'
match = re.search(pattern, content, re.DOTALL)

if match:
    print('Found:', repr(match.group()[:200]))
    new_func = '''def _strip_think(text: str) -> str:
    # Qwen3 outputs think...done or </think>...</think> blocks
    text = re.sub(r"think.*?done", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"think.*?done", "", text, flags=re.DOTALL).strip()
    return text.strip()'''
    content = content[:match.start()] + new_func + content[match.end():]
    with open('C:/Users/ajibe/Jims-AI/modal/modal_reasoning_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replaced reasoning service!')
else:
    print('Not found')
    # Show lines around
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '_strip_think' in line:
            print(f"Line {i}: {repr(line)}")
            if i+1 < len(lines):
                print(f"Line {i+1}: {repr(lines[i+1])}")