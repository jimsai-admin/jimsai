import logging
import os
import re
import hashlib
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

# Attempt torch import for fusion weights
try:
    import torch
except ImportError:
    torch = None

logger = logging.getLogger(__name__)


class SymbolicAugmenter:
    """Light symbolic processing for math, code, causal relations"""

    def augment(self, text: str) -> Dict[str, Any]:
        return {
            "math_normalized": self.normalize_math(text),
            "code_snippets": self.extract_code(text),
            "causal_signals": self.detect_causal(text),
        }

    def normalize_math(self, text: str) -> str:
        # Detect presence of mathematical content
        math_operators = set("=+-*/^()√πθ")
        has_operator = any(c in math_operators for c in text)
        has_math_pattern = bool(re.search(r"\b\d+[xXyY]\b|\b[xXyY]\s*=\s*\d+", text))

        if not (has_operator or has_math_pattern):
            return ""

        # Clean expression spaces and inject implicit multiplications
        normalized = text.strip()
        normalized = re.sub(r"(\d+)([a-zA-Z])", r"\1*\2", normalized)
        normalized = re.sub(r"\s+", " ", normalized)

        # Attempt to normalize using sympy if available
        try:
            from sympy import sympify
            if "=" in normalized:
                parts = normalized.split("=")
                lhs = str(sympify(parts[0].strip()))
                rhs = str(sympify(parts[1].strip()))
                return f"{lhs} = {rhs}"
            else:
                return str(sympify(normalized))
        except Exception:
            return normalized

    def extract_code(self, text: str) -> List[str]:
        # Extract markdown code blocks
        code_blocks = re.findall(
            r"```(?:python|javascript|typescript|c|cpp|json|csv|rust|go)?\s*(.*?)\s*```",
            text,
            re.DOTALL,
        )
        if code_blocks:
            return [block.strip() for block in code_blocks if block.strip()]

        # Fallback to searching for signature keywords at line boundaries
        code_lines = []
        lines = text.split("\n")
        in_code = False
        current_block = []
        for line in lines:
            if re.match(r"^\s*(def|class|import|from|function|const|let|var|if|for|while|return)\b", line):
                current_block.append(line)
                in_code = True
            elif in_code and (line.startswith(" ") or line.startswith("\t") or line.strip() == ""):
                current_block.append(line)
            else:
                if in_code:
                    code_lines.append("\n".join(current_block).strip())
                    current_block = []
                    in_code = False
        if current_block:
            code_lines.append("\n".join(current_block).strip())
        return [c for c in code_lines if c]

    def detect_causal(self, text: str) -> List[Dict[str, str]]:
        causal_signals = []
        # Support common causal connectors
        causal_pattern = re.compile(
            r"(\w+)\s+(causes|triggers|leads to|results in|breaks|blocks|delays|forces)\s+(\w+)",
            re.IGNORECASE,
        )
        for match in causal_pattern.finditer(text):
            causal_signals.append({
                "cause": match.group(1),
                "signal": match.group(2),
                "effect": match.group(3),
            })
        return causal_signals


class AdaptiveHybridEncoder:
    """
    Encoder that fuses semantic, code, and technical embeddings.
    Supports local sentence-transformers / transformers or falls back to remote
    HTTP endpoint (/v1/embed) in serverless Lambda environments.
    """

    def __init__(self, artifact_path: str = None):
        self.current_version = "v1.0"
        self.symbolic = SymbolicAugmenter()
        
        # Weights: 50% Multilingual E5 Semantic, 25% CodeBERT, 25% Jina v3 Technical
        if torch is not None:
            self.fusion_weights = torch.tensor([0.5, 0.25, 0.25], dtype=torch.float32)
        else:
            self.fusion_weights = None

        self.local_mode = True
        try:
            from sentence_transformers import SentenceTransformer
            from transformers import AutoModel, AutoTokenizer

            # 1. Multilingual E5
            self.semantic = SentenceTransformer("intfloat/multilingual-e5-small")
            # 2. CodeBERT
            self.code_model = AutoModel.from_pretrained("microsoft/codebert-base")
            self.code_tokenizer = AutoTokenizer.from_pretrained("microsoft/codebert-base")
            # 3. Jina Embeddings v3
            self.technical = SentenceTransformer("jinaai/jina-embeddings-v3", trust_remote_code=True)

            logger.info("✓ AdaptiveHybridEncoder: Local models loaded successfully.")
        except Exception as e:
            logger.warning(
                f"⚠️ AdaptiveHybridEncoder: Local models unavailable ({e}). "
                f"Configuring remote HTTP embedding endpoints."
            )
            self.local_mode = False
            self.api_url = os.environ.get(
                "JIMS_EMBEDDING_SERVICE_URL", "https://huggingface.co/spaces/jimsai/embeddings"
            )
            self.api_token = os.environ.get("JIMS_EMBEDDING_SERVICE_TOKEN", "")

    def encode(self, raw_text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if metadata is None:
            metadata = {}

        # 1. Parallel / sequential embedding extraction
        if self.local_mode:
            try:
                semantic_emb = self.semantic.encode(raw_text, normalize_embeddings=True)
                code_emb = self._encode_code_local(raw_text)
                tech_emb = self.technical.encode(raw_text, normalize_embeddings=True)
            except Exception as e:
                logger.error(f"Local encoding failed: {e}. Attempting remote fallback.")
                semantic_emb, code_emb, tech_emb = self._encode_remote(raw_text)
        else:
            semantic_emb, code_emb, tech_emb = self._encode_remote(raw_text)

        # 2. Extract symbolic structures
        symbolic_features = self.symbolic.augment(raw_text)

        # 3. Embedding Fusion
        fused = self._fuse_embeddings([semantic_emb, code_emb, tech_emb])

        # 4. Structured extraction via parent extractors
        structured = self._extract_structured(raw_text, metadata, symbolic_features)

        # 5. ID Generation
        signature_id = hashlib.sha256(f"{raw_text}:{str(structured)}".encode()).hexdigest()[:32]

        return {
            "id": signature_id,
            "latent_embedding": fused.tolist() if hasattr(fused, "tolist") else list(fused),
            "structured": structured,
            "abstraction_tags": self._generate_tags(structured, symbolic_features),
            "encoder_version": self.current_version,
            "source_trust": metadata.get("source_trust", 0.75),
            "provenance": {
                "ingestion_time": metadata.get("timestamp") or datetime.utcnow().isoformat(),
                "batch_id": metadata.get("batch_id"),
            },
        }

    def _fuse_embeddings(self, embeddings: List[Any]):
        if torch is not None and self.fusion_weights is not None:
            try:
                stacked = torch.tensor(embeddings, dtype=torch.float32)
                # Norm normalization
                norms = torch.norm(stacked, p=2, dim=1, keepdim=True)
                norms = torch.clamp(norms, min=1e-9)
                normalized_stacked = stacked / norms
                fused = torch.sum(normalized_stacked * self.fusion_weights.unsqueeze(1), dim=0)
                # Final normalization
                fused_norm = torch.norm(fused, p=2)
                if fused_norm > 1e-9:
                    fused = fused / fused_norm
                return fused
            except Exception:
                pass

        # NumPy fallback
        import numpy as np
        stacked = np.array(embeddings, dtype=np.float32)
        weights = np.array([0.5, 0.25, 0.25], dtype=np.float32)
        # Apply normalization to each row
        norms = np.linalg.norm(stacked, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-9, None)
        normalized_stacked = stacked / norms
        fused = np.sum(normalized_stacked * weights[:, np.newaxis], axis=0)
        norm = np.linalg.norm(fused) or 1.0
        return fused / norm

    def _encode_code_local(self, text: str):
        try:
            inputs = self.code_tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
            with torch.no_grad():
                outputs = self.code_model(**inputs)
            embeddings = outputs[0].mean(dim=1).squeeze(0)
            norm = torch.norm(embeddings, p=2)
            if norm > 1e-9:
                embeddings = embeddings / norm
            return embeddings.cpu().numpy()
        except Exception as e:
            logger.error(f"Local CodeBERT encoding error: {e}")
            import numpy as np
            return np.zeros(768, dtype=np.float32)

    def _encode_remote(self, text: str) -> Tuple[List[float], List[float], List[float]]:
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            semantic_vec = self._fetch_remote_vector(text, "intfloat/multilingual-e5-small", headers)
            code_vec = self._fetch_remote_vector(text, "microsoft/codebert-base", headers)
            tech_vec = self._fetch_remote_vector(text, "jinaai/jina-embeddings-v3", headers)

            # Project all vectors to standard 768 dimensions for unified stacked fusion
            return (
                self._project_vector(semantic_vec, 768),
                self._project_vector(code_vec, 768),
                self._project_vector(tech_vec, 768),
            )
        except Exception as e:
            logger.error(f"Remote HTTP embedding call failed: {e}. Projecting deterministic hash vectors.")
            
            # Deterministic hash fallback
            try:
                from .dual_encoder import hash_embedding
                h1 = hash_embedding(text + "::semantic", 768)
                h2 = hash_embedding(text + "::code", 768)
                h3 = hash_embedding(text + "::technical", 768)
                return h1, h2, h3
            except ImportError:
                return ([0.0] * 768, [0.0] * 768, [0.0] * 768)

    def _fetch_remote_vector(self, text: str, model_id: str, headers: Dict[str, str]) -> List[float]:
        import httpx
        url = f"{self.api_url}/v1/embed"
        payload = {"input": text, "model": model_id}
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [[]])[0].get("embedding", [])
        except Exception:
            pass
        return []

    def _project_vector(self, vector: List[float], target_dim: int) -> List[float]:
        if not vector:
            return [0.0] * target_dim
        current_dim = len(vector)
        if current_dim == target_dim:
            return vector
        elif current_dim < target_dim:
            return vector + [0.0] * (target_dim - current_dim)
        else:
            return vector[:target_dim]

    def _extract_structured(self, text: str, metadata: Dict[str, Any], symbolic: Dict[str, Any]) -> Dict[str, Any]:
        entities = []
        relations = []
        causal_chain = []

        try:
            from .dual_encoder import extract_entity_names, extract_sentence_relations, infer_entity_type, stable_id
            for name in extract_entity_names(text):
                entities.append({
                    "id": stable_id("ent", name),
                    "name": name,
                    "type": infer_entity_type(name),
                })
            for subject, predicate, obj, confidence in extract_sentence_relations(text):
                relations.append({
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                    "confidence": confidence,
                })
                if predicate == "causes":
                    causal_chain.append({
                        "cause": subject,
                        "effect": obj,
                        "confidence": confidence,
                    })
        except ImportError:
            # Fallback when running completely outside package imports
            for sig in symbolic.get("causal_signals", []):
                causal_chain.append({
                    "cause": sig["cause"],
                    "effect": sig["effect"],
                    "confidence": 0.85,
                })

        return {
            "entities": entities,
            "relations": relations,
            "causal_chain": causal_chain,
            "is_mathematical": bool(symbolic.get("math_normalized")),
        }

    def _generate_tags(self, structured: Dict[str, Any], symbolic: Dict[str, Any]) -> List[str]:
        tags = ["general"]
        if symbolic.get("math_normalized"):
            tags.append("mathematical")
        if symbolic.get("code_snippets"):
            tags.append("code")
        if structured.get("causal_chain"):
            tags.append("causal")
        return tags
