from prototype.jimsai.encoder.dual_encoder import hash_embedding
import math

def cosine_similarity(v1, v2):
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

# Prototype texts from classifier
prototypes = {
    "FETCH_DOCUMENT": "fetch retrieve download upload attach file document export save read open import load gba fifipamọ nweta chekwaa samu ajiye télécharger document récupérer archivo descargar",
    "SYSTEM_DIAGNOSTIC": "system error status crash failure bug log trace debug issue diagnostic exception problem yọọda nye aka koma diagnostic crash erreur",
    "WORKSPACE_QUERY": "workspace database db affects changed impact query what happens if codebase relation dependency effect consequence causation base de données consulta",
    "CODE_GENERATE": "generate code write function method API create script implementation logic python javascript ruby java cpp testing tests koodu kodi générer du code python écrire une fonction python generar código python escribir una función python 编写用于排序的Python函数 Python代码生成 ソート用のPython関数を書いてください Pythonコード生成 اكتب دالة Python للفرز توليد رمز Python सॉर्टिंग के लिए Python फ़ंक्शन लिखें Python कोड उत्पन्न करें",
    "RUN_CANVAS": "run analyze deep codebase synthesis comprehensive corpus investigation background execution canvas",
    "RUN_INVENTION": "invent design novel architecture create blueprint prototype strategy plan original innovative solution invention",
    "GENERAL_FACT": "general knowledge define explain concept understand information fact learning educational reference",
    "EMOTIONAL_CATCH": "help emotional support stress overwhelmed sad tired anxious upset frustrated struggling difficulty how overwhelm distressed worried concerned scared nervous confused broken unclear incoherent please xqz xyz abc taimako nye aka Je suis stressé Je suis stressé et confus Estoy estresado Estoy estresado y confundido 我感到压力 我感到压力和困惑 ストレスを感じています ストレスを感じていて、混乱しています أشعر بالتوتر أشعر بالتوتر والارتباك मैं तनावग्रस्त हूँ मैं तनावग्रस्त और भ्रमित हूँ",
    "META_INQUIRY": "meta about yourself reasoning explain sources confidence introspection self know capability awareness",
    "OP_ESCAPE_TO_SANDBOX": "zzzz qqqq unknown random nonsense xxxx yyyy wwww vvvv",
}

profile_text = "tell me about myself my profile personal information who am i me"

queries = [
    ("My name is Celestine.", "English"),
    ("Je m'appelle Pierre.", "French"),
    ("Me llamo María.", "Spanish"),
    ("Orúkọ mi ni Adé.", "Yoruba"),
    ("اسمي أحمد.", "Arabic"),
    ("我的名字是小明。", "Chinese"),
]

# Compute prototype embeddings
proto_embeddings = {}
for name, text in prototypes.items():
    proto_embeddings[name] = hash_embedding("passage: " + text, 768)

profile_emb = hash_embedding("passage: " + profile_text, 768)

print("Profile embedding non-zero:", sum(1 for v in profile_emb if v != 0.0))
print()

for query, lang in queries:
    query_emb = hash_embedding("query: " + query, 768)
    print(f"{lang}: '{query}'")
    print(f"  Query non-zero: {sum(1 for v in query_emb if v != 0.0)}")
    
    # Check profile similarity
    profile_sim = cosine_similarity(query_emb, profile_emb)
    print(f"  Profile sim: {profile_sim:.4f}")
    
    # Check intent similarities
    best_intent = None
    best_score = -1
    for name, proto_emb in proto_embeddings.items():
        sim = cosine_similarity(query_emb, proto_emb)
        if sim > best_score:
            best_score = sim
            best_intent = name
    print(f"  Best intent: {best_intent} ({best_score:.4f})")
    print()