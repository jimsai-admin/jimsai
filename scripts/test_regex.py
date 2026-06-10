import re
p = re.compile(r'\bwhat\s+is\s+my\s+name\b', re.IGNORECASE)
print("regex match:", bool(p.search("What is my name?")))

# Also test via the actual compiler
import sys; sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
c = SemanticCompilerRuntime()
ir = c.compile("What is my name?")
print("target_ir:", ir.target_ir)
print("profile_query:", ir.scope_constraints.get("profile_query"))
print("confidence:", ir.confidence)
