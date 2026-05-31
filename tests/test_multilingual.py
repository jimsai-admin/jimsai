"""
Multilingual intent classification tests for SemanticCompiler.

Tests validate that the embedding-based intent classifier generalizes
across multiple languages. Tests are designed to be flexible to account
for natural variance in semantic similarity across language boundaries.
"""

import pytest
from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
from prototype.jimsai.intent_classifier import EmbeddingClassifier


class TestMultilingualBasics:
    """Test core functionality across multiple languages."""

    @pytest.fixture
    def classifier(self):
        """Initialize classifier with multilingual model."""
        return EmbeddingClassifier()

    @pytest.fixture
    def compiler(self):
        """Initialize semantic compiler runtime."""
        return SemanticCompilerRuntime()

    # English Tests
    def test_english_code_generation(self, compiler):
        """English: code generation request."""
        result = compiler.compile("write a python function for sorting")
        assert result.target_ir == "CODE_GENERATE"
        assert result.confidence >= 0.50

    def test_english_emotional(self, compiler):
        """English: emotional distress query."""
        result = compiler.compile("I'm stressed and confused")
        assert result.target_ir == "EMOTIONAL_CATCH"
        assert result.confidence >= 0.50

    # French Tests
    def test_french_code_generation(self, compiler):
        """French: code generation request."""
        result = compiler.compile("Écris une fonction Python pour trier")
        assert result.target_ir == "CODE_GENERATE"
        assert result.confidence >= 0.50

    def test_french_emotional(self, compiler):
        """French: emotional distress query."""
        result = compiler.compile("Je suis stressé et confus")
        assert result.target_ir == "EMOTIONAL_CATCH"
        assert result.confidence >= 0.50

    # Spanish Tests
    def test_spanish_code_generation(self, compiler):
        """Spanish: code generation request."""
        result = compiler.compile("Escribe una función Python para ordenar")
        assert result.target_ir == "CODE_GENERATE"
        assert result.confidence >= 0.50

    def test_spanish_emotional(self, compiler):
        """Spanish: emotional distress query."""
        result = compiler.compile("Estoy estresado y confundido")
        assert result.target_ir == "EMOTIONAL_CATCH"
        assert result.confidence >= 0.50

    # Chinese Tests
    def test_chinese_code_generation(self, classifier):
        """Chinese: code generation request."""
        target, confidence = classifier.classify_intent("编写用于排序的Python函数")
        assert target == "CODE_GENERATE"
        assert confidence >= 0.50

    def test_chinese_emotional(self, classifier):
        """Chinese: emotional distress query."""
        target, confidence = classifier.classify_intent("我感到压力和困惑")
        assert target == "EMOTIONAL_CATCH"
        assert confidence >= 0.50

    # Japanese Tests
    def test_japanese_code_generation(self, classifier):
        """Japanese: code generation request."""
        target, confidence = classifier.classify_intent("ソート用のPython関数を書いてください")
        assert target == "CODE_GENERATE"
        assert confidence >= 0.50

    def test_japanese_emotional(self, classifier):
        """Japanese: emotional distress query."""
        target, confidence = classifier.classify_intent("ストレスを感じていて、混乱しています")
        assert target == "EMOTIONAL_CATCH"
        assert confidence >= 0.50

    # Arabic Tests
    def test_arabic_code_generation(self, classifier):
        """Arabic: code generation request."""
        target, confidence = classifier.classify_intent("اكتب دالة Python للفرز")
        assert target == "CODE_GENERATE"
        assert confidence >= 0.50

    def test_arabic_emotional(self, classifier):
        """Arabic: emotional distress query."""
        target, confidence = classifier.classify_intent("أشعر بالتوتر والارتباك")
        assert target == "EMOTIONAL_CATCH"
        assert confidence >= 0.50

    # Hindi Tests
    def test_hindi_code_generation(self, classifier):
        """Hindi: code generation request."""
        target, confidence = classifier.classify_intent("सॉर्टिंग के लिए Python फ़ंक्शन लिखें")
        assert target == "CODE_GENERATE"
        assert confidence >= 0.50

    def test_hindi_emotional(self, classifier):
        """Hindi: emotional distress query."""
        target, confidence = classifier.classify_intent("मैं तनावग्रस्त और भ्रमित हूँ")
        assert target == "EMOTIONAL_CATCH"
        assert confidence >= 0.50


class TestLanguageConsistency:
    """Test that intent routing is consistent across languages."""

    @pytest.fixture
    def classifier(self):
        """Initialize classifier."""
        return EmbeddingClassifier()

    def test_code_generation_consistency(self, classifier):
        """Verify code generation intent recognized across languages."""
        queries = [
            "generate python code",  # English
            "générer du code python",  # French
            "generar código python",  # Spanish
            "Python代码生成",  # Chinese
            "Pythonコード生成",  # Japanese
            "توليد رمز Python",  # Arabic
            "Python कोड उत्पन्न करें",  # Hindi
        ]
        
        for query in queries:
            target, confidence = classifier.classify_intent(query)
            assert target == "CODE_GENERATE", f"Failed for: {query}"
            assert confidence >= 0.50, f"Low confidence for: {query}"

    def test_emotional_consistency(self, classifier):
        """Verify emotional intent recognized across languages."""
        queries = [
            "I'm stressed",  # English
            "Je suis stressé",  # French
            "Estoy estresado",  # Spanish
            "我感到压力",  # Chinese
            "ストレスを感じています",  # Japanese
            "أشعر بالتوتر",  # Arabic
            "मैं तनावग्रस्त हूँ",  # Hindi
        ]
        
        for query in queries:
            target, confidence = classifier.classify_intent(query)
            assert target == "EMOTIONAL_CATCH", f"Failed for: {query}"
            assert confidence >= 0.50, f"Low confidence for: {query}"

    def test_gibberish_consistency(self, classifier):
        """Verify gibberish routes to sandbox across languages."""
        queries = [
            "zzzz qqqq",
            "xxxx yyyy",
            "wwww vvvv",
        ]
        
        for query in queries:
            target, confidence = classifier.classify_intent(query)
            assert target == "OP_ESCAPE_TO_SANDBOX"
