# Fix _strip_think function in modal services
import re

# Read the file
with open('C:/Users/ajibe/Jims-AI/modal/modal_renderer_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the _strip_think function
# The current pattern uses special Unicode characters
# We need to match the exact pattern in the file

# Let's find the function using regex
pattern = r'(def _strip_think\(text: str\) -> str:\n\s*return re\.sub\(r".*?".*?\.strip\(\))'
match = re.search(pattern, content, re.DOTALL)

if match:
    print("Found existing function:")
    print(repr(match.group()[:200]))
    
    # Replace with corrected version
    new_func = '''def _strip_think(text: str) -> str:
    # Qwen3 outputs think...done or </think>...</think> blocks
    text = re.sub(r"think.*?done", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"think.*?done", "", text, flags=re.DOTALL).strip()
    return text.strip()'''
    
    content = content[:match.start()] + new_func + content[match.end():]
    
    with open('C:/Users/ajibe/Jims-AI/modal/modal_renderer_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replaced!")
else:
    print("Pattern not found")
    # Show lines around line 101
    lines = content.split('\n')
    for i in range(100, 105):
        if i < len(lines):
            print(f"{i+1}: {repr(lines[i])}")