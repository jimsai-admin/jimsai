"""
Creative Writing Capability Adapter

Generates nuanced language, poetic/technical/conversational text,
with optional T2 usage for complex language.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CreativeRequest:
    """Request for creative content generation"""
    prompt: str
    style: str  # "poetic" | "technical" | "conversational" | "academic"
    length: str = "medium"  # "short" | "medium" | "long"
    mood: Optional[str] = None
    constraints: Dict[str, Any] = None  # Style/content rules
    max_tokens: int = 1000
    use_t2: bool = True  # Override T2 availability check


@dataclass
class CreativeOutput:
    """Generated creative content"""
    content: str
    style: str
    model_used: str  # "deterministic" | "t2_renderer"
    confidence: float
    verification_status: str
    execution_time_ms: float


class CreativeWritingAdapter:
    """Generate creative, nuanced language output"""
    
    def __init__(self, t2_renderer=None, csse=None, event_store=None):
        self.t2_renderer = t2_renderer
        self.csse = csse
        self.event_store = event_store
        
        # Style templates for deterministic generation
        self.style_templates = {
            "poetic": {
                "elements": ["metaphor", "imagery", "rhythm"],
                "openings": [
                    "Like {subject}, {content}",
                    "In the garden of {concept}, {content}",
                    "Where {subject} dwells, {content}",
                ],
            },
            "technical": {
                "elements": ["precision", "structure", "clarity"],
                "openings": [
                    "Precisely, {content}",
                    "In technical terms, {content}",
                    "The mechanism operates as follows: {content}",
                ],
            },
            "conversational": {
                "elements": ["warmth", "accessibility", "directness"],
                "openings": [
                    "So here's the thing about {subject}: {content}",
                    "Think of it this way - {content}",
                    "Let me share something with you: {content}",
                ],
            },
            "academic": {
                "elements": ["precision", "evidence", "formality"],
                "openings": [
                    "In scholarly discourse, {content}",
                    "The literature suggests that {content}",
                    "Contemporary understanding indicates that {content}",
                ],
            },
        }
    
    async def generate(
        self,
        request: CreativeRequest,
        trace=None,
        workspace_id=None
    ) -> CreativeOutput:
        """
        Generate creative content
        
        Args:
            request: Creative generation request
            trace: Execution trace for logging
            workspace_id: For multi-tenancy
            
        Returns:
            Generated creative content with metadata
        """
        
        import time
        start_time = time.time()
        
        # Decision: Use deterministic or T2?
        should_use_deterministic = await self._can_use_deterministic(request, trace)
        
        if should_use_deterministic and not request.use_t2:
            logger.info(f"Using deterministic generation for {request.style}")
            output = await self._generate_deterministic(request)
            model_used = "deterministic"
        else:
            logger.info(f"Using T2 renderer for {request.style}")
            output = await self._generate_with_t2(request)
            model_used = "t2_renderer"
        
        # Verify creative bounds
        verified = await self._verify_creative(output, request)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        result = CreativeOutput(
            content=verified["content"],
            style=request.style,
            model_used=model_used,
            confidence=verified["confidence"],
            verification_status=verified["status"],
            execution_time_ms=execution_time_ms,
        )
        
        # Log to event store
        if self.event_store:
            await self._log_to_event_store(result, request, workspace_id)
        
        return result
    
    async def _can_use_deterministic(
        self,
        request: CreativeRequest,
        trace
    ) -> bool:
        """
        Determine if deterministic generation is sufficient
        
        Skip T2 when:
        - Style is straightforward (not poetic/complex)
        - Memory has high-confidence templates
        - Content doesn't require novel fluency
        """
        
        # Poetic style usually needs T2
        if request.style == "poetic":
            return False
        
        # If trace has very high memory confidence
        if trace and trace.memory_confidence > 0.95:
            return True
        
        # Long content might need T2 for fluency
        if request.length == "long":
            return False
        
        # Simple styles can be deterministic
        if request.style in ["technical", "academic"] and request.length in ["short", "medium"]:
            return True
        
        return False
    
    async def _generate_deterministic(
        self,
        request: CreativeRequest
    ) -> str:
        """
        Generate using templates + CSSE rendering
        
        No T2 dependency - deterministic style application
        """
        
        if not self.csse:
            return request.prompt  # Fallback: return input as-is
        
        # Apply style transformation
        styled_content = await self.csse.render_with_style(
            request.prompt,
            style=request.style,
            constraints=request.constraints
        )
        
        return styled_content
    
    async def _generate_with_t2(
        self,
        request: CreativeRequest
    ) -> str:
        """
        Generate using T2 renderer (Groq) for fluency
        
        T2 is bounded to style + constraint satisfaction
        """
        
        if not self.t2_renderer:
            # Fallback to deterministic
            return await self._generate_deterministic(request)
        
        # Build system prompt from style
        system_prompt = self._build_style_prompt(request)
        
        # Call T2 with style constraints
        response = await self.t2_renderer.call(
            prompt=request.prompt,
            system=system_prompt,
            temperature=0.7 if request.style == "poetic" else 0.5,
            max_tokens=request.max_tokens
        )
        
        return response.text if hasattr(response, 'text') else str(response)
    
    def _build_style_prompt(self, request: CreativeRequest) -> str:
        """Build system prompt for T2 based on style"""
        
        base = f"You are generating {request.style} content."
        
        style_guidance = {
            "poetic": """
                Use metaphors, imagery, and rhythm.
                Prioritize beauty and emotional resonance.
                Employ varied sentence structure.
                Create vivid mental images.
            """,
            "technical": """
                Prioritize clarity and precision.
                Use domain-specific terminology accurately.
                Organize ideas logically.
                Avoid ambiguity.
            """,
            "conversational": """
                Write as if speaking to a friend.
                Use accessible language.
                Include natural transitions.
                Feel warm and approachable.
            """,
            "academic": """
                Use formal language and proper terminology.
                Cite or reference ideas where appropriate.
                Structure arguments logically.
                Maintain scholarly tone.
            """,
        }
        
        guidance = style_guidance.get(request.style, "")
        
        constraints = ""
        if request.constraints:
            constraints = "Additional constraints:\n"
            for key, value in request.constraints.items():
                constraints += f"- {key}: {value}\n"
        
        return f"{base}\n{guidance}\n{constraints}"
    
    async def _verify_creative(
        self,
        content: str,
        request: CreativeRequest
    ) -> Dict[str, Any]:
        """
        Verify creative bounds
        
        Check:
        - Content respects style constraints
        - No factual claims made (or sourced)
        - Appropriate length
        - No harmful content
        """
        
        if not self.csse:
            return {
                "content": content,
                "confidence": 0.7,
                "status": "unverified",
            }
        
        verification = await self.csse.verify_creative(
            content,
            style_constraints=request.constraints,
            allow_speculation=True,  # Creative content can speculate
            require_sourced_facts=False,  # Creative can imagine
            max_length=request.max_tokens * 1.2,
        )
        
        return {
            "content": verification.get("content", content),
            "confidence": verification.get("confidence", 0.8),
            "status": verification.get("status", "verified"),
        }
    
    async def _log_to_event_store(
        self,
        result: CreativeOutput,
        request: CreativeRequest,
        workspace_id
    ):
        """Log generation to event store for training"""
        
        from .eventing.events import CreativeWritingGenerated
        
        event = CreativeWritingGenerated(
            aggregate_id=workspace_id or "system",
            writing_id=str(__import__('uuid').uuid4()),
            workspace_id=workspace_id,
            output=result.content,
            style=request.style,
            confidence=result.confidence,
            verification_status=result.verification_status,
            model_used=result.model_used,
        )
        
        await self.event_store.append(event)


# Style templates library
class StyleTemplateLibrary:
    """Library of pre-built style templates"""
    
    @staticmethod
    def get_poetic_variations(subject: str) -> list:
        """Generate poetic variations of a subject"""
        return [
            f"Like {subject}, {{}}.  ",
            f"In the realm of {subject}, {{}}.",
            f"Where {subject} dwells, {{}}.  ",
            f"{subject} whispers that {{}}.",
            f"Through the lens of {subject}, {{}}.  ",
        ]
    
    @staticmethod
    def get_technical_variations(topic: str) -> list:
        """Generate technical variations of a topic"""
        return [
            f"Regarding {topic}: {{}}",
            f"The {topic} mechanism operates as follows: {{}}",
            f"Technically speaking, {topic} {{}}",
            f"In terms of {topic}, {{}}",
            f"The specifications of {topic} dictate that {{}}",
        ]
    
    @staticmethod
    def get_conversational_variations(subject: str) -> list:
        """Generate conversational variations"""
        return [
            f"So about {subject} - {{}}",
            f"Here's the thing with {subject}: {{}}",
            f"Let me tell you about {subject}: {{}}",
            f"You know what's interesting about {subject}? {{}}",
            f"Think of {subject} like this: {{}}",
        ]
    
    @staticmethod
    def get_academic_variations(topic: str) -> list:
        """Generate academic variations"""
        return [
            f"In scholarly analysis of {topic}, {{}}",
            f"The academic consensus regarding {topic} suggests {{}}",
            f"Contemporary research on {topic} indicates {{}}",
            f"The theoretical framework of {topic} posits that {{}}",
            f"Within the domain of {topic}, {{}}",
        ]
