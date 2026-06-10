import re
import hashlib

def hash_embedding(text: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in re.findall(r"[\w\.]+", text.lower(), flags=re.UNICODE):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[idx] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]

import math

profile_text = (
    "tell me about myself my profile personal information who am i me "
    "je m'appelle comment je m'appelle mon nom mon profil mes informations "
    "me llamo cómo me llamo mi nombre mi perfil mi información "
    "orúkọ mi ni kí ni orúkọ mi ìpínlẹ̀kọ ọrọ́ ẹ̀dá míi "
    "اسمي ما هو اسمي ملفي الشخصي معلوماتي "
    "我的名字 我的名字是什么 我的个人资料 我的信息 "
    "私の名前 私の名前は何ですか 私のプロフィール 私の情報 "
    "내 이름은 내 프로필 내 정보 "
)

queries = [
    ("My name is Celestine.", "English"),
    ("Je m'appelle Pierre.", "French"),
    ("Me llamo María.", "Spanish"),
]

print("Profile tokens:")
profile_tokens = re.findall(r"[\w\.]+", profile_text.lower(), flags=re.UNICODE)
print(profile_tokens[:30])
print(f"Total: {len(profile_tokens)}")

for query, lang in queries:
    print(f"\n{lang} query: '{query}'")
    query_tokens = re.findall(r"[\w\.]+", ("query: " + query).lower(), flags=re.UNICODE)
    print(f"  Tokens: {query_tokens}")
    
    # Check overlap
    profile_token_set = set(profile_tokens)
    query_token_set = set(query_tokens)
    overlap = profile_token_set & query_token_set
    print(f"  Overlap: {overlap}")

# Check hash indices for overlapping tokens
print("\nHash indices for key tokens:")
for token in ["my", "name", "is", "celestine", "je", "m'appelle", "comment", "me", "llamo", "como", "mi", "nombre"]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:2], "big") % 64
    sign = 1.0 if digest[2] % 2 == 0 else -1.0
    print(f"  {token}: idx={idx}, sign={sign}")