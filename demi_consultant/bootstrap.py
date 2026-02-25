from __future__ import annotations

from demi_consultant.ai.guardrails import Guardrails
from demi_consultant.ai.openai_client import OpenAIClient
from demi_consultant.core.config import Settings
from demi_consultant.integrations.crm.crm_service import build_crm_service
from demi_consultant.knowledge.knowledge_loader import get_knowledge_bundle
from demi_consultant.services.consultation_service import ConsultationService
from demi_consultant.services.context_intelligence_service import ContextIntelligenceService
from demi_consultant.services.conversion_engine import ConversionEngine
from demi_consultant.services.interaction_guard_service import InteractionGuardService
from demi_consultant.services.memory_service import MemoryService
from demi_consultant.services.onboarding_service import OnboardingService
from demi_consultant.services.short_answer_cache import ShortAnswerCache
from demi_consultant.services.skin_progress_service import SkinProgressService
from demi_consultant.services.token_guard import TokenGuard
from demi_consultant.transport.rate_limit import RateLimiter


def build_consultation_service(
    settings: Settings,
    *,
    rate_limiter: RateLimiter | None = None,
) -> ConsultationService:
    memory_service = MemoryService(max_history_messages=20)
    guardrails = Guardrails()
    openai_client = OpenAIClient(settings=settings, retries=2)
    context_intelligence = ContextIntelligenceService()
    token_guard = TokenGuard(
        max_context_tokens=settings.max_context_tokens,
        keep_messages=settings.max_context_messages,
    )

    knowledge = get_knowledge_bundle()
    crm_service = build_crm_service(
        enabled=settings.crm_enabled,
        storage=settings.crm_storage,
        json_path=settings.crm_json_path,
    )

    conversion_engine = ConversionEngine(
        conversion_rules=knowledge.conversion_rules,
        human_contact=settings.human_contact,
    )
    onboarding_service = OnboardingService()
    limiter = rate_limiter or RateLimiter(interval_seconds=settings.rate_limit_seconds)
    interaction_guard = InteractionGuardService(settings=settings, rate_limiter=limiter)
    short_answer_cache = ShortAnswerCache(ttl_seconds=6 * 60 * 60)
    skin_progress_service = SkinProgressService(openai_client=openai_client)

    return ConsultationService(
        memory_service=memory_service,
        openai_client=openai_client,
        guardrails=guardrails,
        context_intelligence_service=context_intelligence,
        token_guard=token_guard,
        conversion_engine=conversion_engine,
        onboarding_service=onboarding_service,
        interaction_guard_service=interaction_guard,
        short_answer_cache=short_answer_cache,
        crm_service=crm_service,
        knowledge=knowledge,
        skin_progress_service=skin_progress_service,
    )
