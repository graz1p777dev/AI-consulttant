from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from time import perf_counter
from typing import Any

from demi_consultant.ai.guardrails import Guardrails
from demi_consultant.ai.openai_client import OpenAIClient
from demi_consultant.ai.prompts import build_system_prompt
from demi_consultant.core.exceptions import AIClientError, EmptyResponseError, GuardrailViolation
from demi_consultant.core.logger import log_extra
from demi_consultant.integrations.crm.crm_service import CRMService
from demi_consultant.knowledge.knowledge_loader import KnowledgeBundle
from demi_consultant.services.context_intelligence_service import ContextIntelligenceService
from demi_consultant.services.conversion_engine import ConversionEngine
from demi_consultant.services.interaction_guard_service import InputGuardDecision, InteractionGuardService
from demi_consultant.services.memory_service import MemoryService
from demi_consultant.services.onboarding_service import OnboardingService
from demi_consultant.services.short_answer_cache import ShortAnswerCache
from demi_consultant.services.skin_progress_service import SkinProgressService
from demi_consultant.services.token_guard import TokenGuard
from demi_consultant.state.fsm import ChatMode
from demi_consultant.state.user_session import UserSession
from demi_consultant.utils.text_utils import clean_response, is_simple_decline

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ResponseTuning:
    runtime_guidance: str
    short_mode: bool
    beginner_mode: bool
    low_confidence: bool
    simple_question: bool
    routine_request: bool


class ConsultationService:
    """Core domain service reused by Telegram/WhatsApp/Instagram adapters."""

    _EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
    _DOUBT_MARKERS: tuple[str, ...] = (
        "сомнева",
        "не уверен",
        "не уверена",
        "не соглас",
        "не похоже",
        "вдруг",
        "может не",
        "не такая",
        "ошиб",
    )
    _BEGINNER_MARKERS: tuple[str, ...] = (
        "не пользуюсь уходом",
        "никогда не пользовалась косметикой",
        "никогда не пользовался косметикой",
        "хочу начать уход",
        "с чего начать уход",
        "я новичок",
    )
    _WORKED_MARKERS: tuple[str, ...] = (
        "подошло",
        "помогло",
        "стало лучше",
        "улучшилось",
        "работает",
    )
    _NOT_WORKED_MARKERS: tuple[str, ...] = (
        "не подошло",
        "не помогло",
        "стало хуже",
        "ухудшилось",
        "раздражение",
        "сыпь",
    )
    _ROUTINE_REQUEST_MARKERS: tuple[str, ...] = (
        "собрать уход",
        "уход в 1 экран",
        "рутину",
        "routine",
        "утро и вечер",
        "утром и вечером",
    )
    _PROGRESS_FOLLOW_UP_MARKERS: tuple[str, ...] = (
        "как кожа изменилась",
        "есть прогресс",
        "как динамика",
        "как изменение",
        "стало лучше",
        "стало хуже",
    )
    _AMBIGUOUS_MARKERS: tuple[str, ...] = (
        "вдруг",
        "кажется",
        "не знаю",
        "сомнева",
        "может быть",
    )
    _DOMAIN_KEYWORDS: tuple[str, ...] = (
        "кожа",
        "уход",
        "космет",
        "ингредиент",
        "состав",
        "лицо",
        "акне",
        "прыщ",
        "пигмент",
        "spf",
        "ретинол",
        "ниацинамид",
    )
    _OFFTOPIC_MARKERS: tuple[str, ...] = (
        "политик",
        "президент",
        "выборы",
        "философ",
        "религ",
        "крипт",
        "ставк",
        "спорт",
        "футбол",
        "анекдот",
        "гороскоп",
        "астролог",
        "программирован",
        "python",
        "javascript",
        "функцию на питон",
        "код",
        "как дела",
        "погода",
        "новости",
    )
    _FOLLOW_UP_SHORT_MARKERS: tuple[str, ...] = (
        "давай",
        "ок",
        "окей",
        "а если",
        "и если",
        "а дальше",
        "что дальше",
        "и?",
        "а?",
        "угу",
    )
    _COMPLAINT_MARKERS: tuple[str, ...] = (
        "у меня",
        "кожа",
        "шерша",
        "стяг",
        "сухая",
        "жирная",
        "прыщ",
        "раздраж",
        "красне",
        "чеш",
        "жжет",
        "жжёт",
    )
    _HUMAN_CONTACT_MARKERS: tuple[str, ...] = (
        "реальным косметолог",
        "живым косметолог",
        "связаться с косметолог",
        "менеджер",
        "живой специалист",
    )
    _UNCERTAINTY_MARKERS: tuple[str, ...] = (
        "возможно",
        "может",
        "скорее",
        "по описанию",
        "без фото сложно",
    )
    _HEDGE_MARKERS: tuple[str, ...] = (
        "обычно",
        "чаще",
        "многие",
        "может",
        "возможно",
        "иногда",
    )
    _SYMPTOM_MARKERS: dict[str, tuple[str, ...]] = {
        "peeling": ("шелуш",),
        "tightness": ("стянут", "стянутост"),
        "sensitivity": ("чувствитель", "реакц", "раздраж", "жжет", "жжение", "щиплет"),
        "appearance": ("внешн", "выгляд", "на фото", "блеск", "поры", "тон"),
    }
    _SYMPTOM_SOFT_LINES: dict[str, str] = {
        "peeling": "При сухой коже обычно бывает шелушение.",
        "tightness": "Чаще всего сухая кожа сопровождается ощущением стянутости после умывания.",
        "sensitivity": "Многие замечают чувствительность кожи при ослабленном барьере.",
        "appearance": "Без фото я не оцениваю внешний вид кожи.",
    }
    _CTA_START_MARKERS: tuple[str, ...] = (
        "если хотите",
        "если нужно",
        "если удобно",
        "могу",
        "подключу менеджера",
        "передам диалог",
        "при желании",
    )

    _FOLLOW_UP_PROMPT_MARKERS: tuple[str, ...] = (
        "хотите, можем разобрать",
        "если нужно, могу подобрать уход",
        "могу также разобрать",
        "если появятся вопросы по коже",
    )

    _SKIN_TYPE_MARKERS: tuple[str, ...] = (
        "тип кожи",
        "жирная",
        "сухая",
        "комбинирован",
        "чувствительн",
    )

    _PROBLEM_MARKERS: tuple[str, ...] = (
        "акне",
        "прыщ",
        "пигмент",
        "постакне",
        "краснота",
        "сухость",
        "шелуш",
        "черные точки",
        "чёрные точки",
        "морщин",
        "раздраж",
        "жирност",
    )

    _INGREDIENT_MARKERS: tuple[str, ...] = (
        "состав",
        "ингредиент",
        "inci",
    )

    _ACTIVE_INGREDIENTS: tuple[str, ...] = (
        "ниацинамид",
        "азелаиновая кислота",
        "салициловая кислота",
        "гликолевая кислота",
        "молочная кислота",
        "ретинол",
        "ретиналь",
        "пептиды",
        "витамин c",
        "церамиды",
        "гиалуроновая кислота",
        "пантенол",
        "spf",
        "цинк",
    )

    _REACTION_STARTERS: tuple[str, ...] = (
        "такое бывает довольно часто",
        "понимаю, такие изменения кожи",
        "очень хороший вопрос",
        "хороший вопрос — тут важно разобрать подробнее",
        "спасибо за фото",
        "понимаю ваш запрос",
        "вы правы, без фото сложно оценить точно",
    )

    _SUPPORT_CLOSINGS: tuple[str, ...] = (
        "Если появятся вопросы по коже — я рядом 🤍",
        "Если хотите, можем спокойно уточнить детали и подстроить уход под Вас.",
    )
    _EDUCATIONAL_CLOSINGS: tuple[str, ...] = (
        "Если хотите, могу кратко объяснить, как понять, что уход Вам подходит.",
        "Могу также разобрать Ваш текущий уход и убрать лишние шаги.",
    )
    _CONVERSION_CLOSINGS: tuple[str, ...] = (
        "Если хотите, помогу перейти к подбору по бюджету и наличию.",
    )
    _SOFT_CLOSINGS: tuple[str, ...] = (
        "Если хотите, можем разобрать это глубже или перейти к другой теме ухода.",
        "Если нужно, могу подобрать уход под Вашу кожу без лишних средств.",
        "Могу также разобрать Ваш текущий уход или помочь определить тип кожи.",
        "Если появятся вопросы по коже — я рядом 🤍",
        *_SUPPORT_CLOSINGS,
        *_EDUCATIONAL_CLOSINGS,
        *_CONVERSION_CLOSINGS,
    )

    _PRACTICAL_MARKERS: tuple[str, ...] = (
        "практически",
        "добав",
        "уменьш",
        "патч-тест",
        "spf",
        "частот",
        "провер",
        "нанос",
        "начните",
    )

    _DISALLOWED_GPT_STYLE_PHRASES: tuple[str, ...] = (
        "основной ответ",
        "активы которые рекомендую",
        "вероятный тип",
    )
    _BUREAUCRATIC_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"(?i)\bрекомендуется\b"), "лучше"),
        (re.compile(r"(?i)\bцелесообразно\b"), "лучше"),
        (re.compile(r"(?i)\bнеобходимо\b"), "лучше"),
        (re.compile(r"(?i)\bследует\b"), "лучше"),
        (re.compile(r"(?i)\bв рамках\b"), "по"),
        (re.compile(r"(?i)\bданный\b"), "этот"),
    )
    _MEDICAL_TO_SIMPLE: tuple[tuple[str, str], ...] = (
        ("трансэпидермальная потеря влаги", "потеря влаги"),
        ("нарушение липидного барьера", "ослабленный защитный слой кожи"),
        ("ирритант", "раздражающий компонент"),
        ("комедогенный", "может забивать поры"),
        ("эксфолиация", "мягкое отшелушивание"),
        ("окклюзия", "защитный слой"),
        ("фотопротекция", "защита от солнца"),
    )
    _PLAIN_TECH_MARKERS: tuple[str, ...] = (
        "барьер",
        "трансэпидерм",
        "липид",
        "ирритант",
        "комедоген",
        "эксфоли",
        "окклюзи",
        "фотопротек",
    )
    _ACTIVE_PRIORITY: tuple[str, ...] = (
        "spf",
        "церамиды",
        "гиалуроновая кислота",
        "пантенол",
        "ниацинамид",
        "ретинол",
        "ретиналь",
    )
    _EXPLICIT_PURCHASE_MARKERS: tuple[str, ...] = (
        "купить",
        "в наличии",
        "сколько стоит",
        "цена",
        "стоимость",
        "заказать",
        "оформить",
    )

    _MENU_CONSULTATION_LABELS = {
        "🔘 консультация",
        "консультация",
    }
    _MENU_SKIN_TYPE_LABELS = {
        "🔘 определить тип кожи",
        "определить тип кожи",
        "тип кожи",
    }
    _MENU_PROBLEM_LABELS = {
        "🔘 разобрать проблему",
        "разобрать проблему",
    }

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        openai_client: OpenAIClient,
        guardrails: Guardrails,
        context_intelligence_service: ContextIntelligenceService,
        token_guard: TokenGuard,
        conversion_engine: ConversionEngine,
        onboarding_service: OnboardingService,
        interaction_guard_service: InteractionGuardService,
        short_answer_cache: ShortAnswerCache,
        crm_service: CRMService,
        knowledge: KnowledgeBundle,
        skin_progress_service: SkinProgressService,
    ) -> None:
        self._memory = memory_service
        self._openai_client = openai_client
        self._guardrails = guardrails
        self._context_intelligence = context_intelligence_service
        self._token_guard = token_guard
        self._conversion_engine = conversion_engine
        self._onboarding_service = onboarding_service
        self._interaction_guard = interaction_guard_service
        self._short_answer_cache = short_answer_cache
        self._crm = crm_service
        self._knowledge = knowledge
        self._skin_progress = skin_progress_service

    def get_session(self, user_id: str) -> UserSession:
        return self._memory.get_or_create_session(user_id)

    def start_onboarding(self, user_id: str) -> None:
        session = self._memory.get_or_create_session(user_id)
        session.reset_onboarding()

    def set_mode(self, user_id: str, mode: ChatMode) -> None:
        session = self._memory.get_or_create_session(user_id)
        session.set_mode(mode)
        session.waiting_for_photo = False

    def get_mode(self, user_id: str) -> ChatMode:
        return self._memory.get_or_create_session(user_id).mode

    async def process_message(
        self,
        *,
        user_id: str,
        text: str,
        channel: str,
        event_ts: float | None = None,
    ) -> str | None:
        started_at = perf_counter()
        session = self._memory.get_or_create_session(user_id)

        safety = self._interaction_guard.check_text(
            session,
            user_id,
            text,
            event_ts=event_ts,
            onboarding_incomplete=not session.onboarding_completed,
        )
        if safety.ignore:
            logger.info(
                "Ignored repeated message",
                extra=log_extra(channel=channel, user_id=user_id, started_at=started_at),
            )
            return None
        if not safety.allowed:
            return safety.response

        onboarding = self._onboarding_service.handle_text(session, text)
        if onboarding.handled:
            if onboarding.reply:
                self._memory.remember_user_message(user_id, text)
                self._memory.remember_assistant_message(user_id, onboarding.reply)
                return onboarding.reply
            return None

        menu_reply = self._handle_menu_selection(user_id, text)
        if menu_reply:
            self._memory.remember_user_message(user_id, text)
            self._memory.remember_assistant_message(user_id, menu_reply)
            return menu_reply

        if self._is_strict_domain_offtopic(text):
            redirect_reply = self._soft_domain_redirect(text)
            self._memory.remember_user_message(user_id, text)
            self._memory.remember_assistant_message(user_id, redirect_reply)
            return redirect_reply

        verdict = self._guardrails.validate_user_text(text)
        if not verdict.allowed:
            redirect_reply = self._soft_domain_redirect(text, fallback=verdict.message)
            self._memory.remember_user_message(user_id, text)
            self._memory.remember_assistant_message(user_id, redirect_reply)
            return redirect_reply

        analysis_text = self._smooth_user_intent(text, session)

        self._mark_consultation_started(user_id, session, channel)
        response_mode = self._resolve_response_mode(session, analysis_text)

        if self._should_close_follow_up(session, text):
            self._memory.remember_user_message(user_id, text)
            close_reply = "Если появятся вопросы по коже — я рядом 🤍"
            self._memory.remember_assistant_message(user_id, close_reply)
            return close_reply

        session = self._memory.remember_user_message(user_id, text)
        self._capture_profile_signals(user_id, session, analysis_text, channel)
        tuning = self._build_response_tuning(
            session=session,
            user_text=analysis_text,
            source_user_text=text,
            mode=response_mode,
            has_photo=False,
        )
        if self._is_progress_follow_up(text) and len(session.progress_photos) < 2:
            progress_reply = self._finalize_reply(
                response_mode,
                text,
                "Понимаю Ваш вопрос о динамике кожи.\n\n"
                "Чтобы оценить изменения точнее, нужен ориентир: фото «до» и текущее фото в похожем свете.\n\n"
                "Если хотите, отправьте новое фото, и я кратко сравню, что изменилось.",
                session,
                has_photo=False,
                short_mode=tuning.short_mode,
                beginner_mode=tuning.beginner_mode,
                low_confidence=tuning.low_confidence,
                simple_question=tuning.simple_question,
                routine_request=tuning.routine_request,
            )
            self._memory.remember_assistant_message(user_id, progress_reply)
            return progress_reply

        cached_answer = self._short_answer_cache.match(text)
        if cached_answer:
            final_cached = self._finalize_reply(
                response_mode,
                text,
                cached_answer,
                session,
                has_photo=False,
                short_mode=tuning.short_mode,
                beginner_mode=tuning.beginner_mode,
                low_confidence=tuning.low_confidence,
                simple_question=tuning.simple_question,
                routine_request=tuning.routine_request,
            )
            final_cached = self._apply_conversion(user_id, session, text, final_cached, channel)
            self._memory.remember_assistant_message(user_id, final_cached)
            self._store_recommendation(user_id, session, response_mode, final_cached)
            return final_cached

        history = self._token_guard.trim_history(self._memory.get_context_history(user_id), session)
        payload = [{"role": turn.role, "content": turn.content} for turn in history]

        system_prompt = build_system_prompt(
            response_mode,
            session,
            self._knowledge,
            runtime_guidance=tuning.runtime_guidance,
        )

        max_tokens, verbosity = self._response_profile(
            response_mode,
            analysis_text,
            safety,
            short_mode=tuning.short_mode,
            beginner_mode=tuning.beginner_mode,
        )

        try:
            raw_reply = await self._openai_client.generate_reply(
                system_prompt=system_prompt,
                dialogue=payload,
                max_output_tokens=max_tokens,
                verbosity=verbosity,
            )
            safe_reply = self._guardrails.validate_model_response(raw_reply)
        except (GuardrailViolation, EmptyResponseError, AIClientError) as exc:
            logger.warning(
                "Model fallback used: %s",
                exc,
                extra=log_extra(channel=channel, user_id=user_id, started_at=started_at),
            )
            safe_reply = self._technical_pause_fallback()

        final_reply = self._finalize_reply(
            response_mode,
            text,
            safe_reply,
            session,
            has_photo=False,
            short_mode=tuning.short_mode,
            beginner_mode=tuning.beginner_mode,
            low_confidence=tuning.low_confidence,
            simple_question=tuning.simple_question,
            routine_request=tuning.routine_request,
        )
        final_reply = self._apply_conversion(user_id, session, text, final_reply, channel)
        self._memory.remember_assistant_message(user_id, final_reply)
        self._store_recommendation(user_id, session, response_mode, final_reply)
        return final_reply

    async def process_photo(
        self,
        *,
        user_id: str,
        image_bytes: bytes,
        caption: str | None,
        channel: str,
        image_mime_type: str = "image/jpeg",
        event_ts: float | None = None,
    ) -> str | None:
        started_at = perf_counter()
        caption_text = (caption or "").strip()
        session = self._memory.get_or_create_session(user_id)

        safety = self._interaction_guard.check_image(
            session,
            user_id,
            caption=caption_text,
            image_size=len(image_bytes),
            event_ts=event_ts,
        )
        if safety.ignore:
            return None
        if not safety.allowed:
            return safety.response

        onboarding = self._onboarding_service.handle_text(session, caption_text or "фото")
        if onboarding.handled:
            if onboarding.reply:
                self._memory.remember_user_message(user_id, caption_text or "[Фото]")
                self._memory.remember_assistant_message(user_id, onboarding.reply)
                return onboarding.reply
            return None

        user_text = caption_text or "Пользователь отправил фото лица для консультации."
        verdict = self._guardrails.validate_user_text(user_text)
        if not verdict.allowed:
            return verdict.message or "Я консультирую по уходу за кожей лица."

        self._mark_consultation_started(user_id, session, channel)

        session = self._memory.remember_user_message(user_id, f"[Фото] {user_text}")
        session.add_progress_photo(image_bytes=image_bytes, mime_type=image_mime_type, caption=caption_text or None)
        self._capture_profile_signals(user_id, session, user_text, channel)

        response_mode = self._resolve_response_mode(session, user_text)
        tuning = self._build_response_tuning(
            session=session,
            user_text=user_text,
            source_user_text=user_text,
            mode=response_mode,
            has_photo=True,
        )

        if self._is_progress_request(user_text) and len(session.progress_photos) >= 2:
            previous = session.progress_photos[-2]
            current = session.progress_photos[-1]
            try:
                comparison = await self._skin_progress.compare_photos(
                    previous.image_bytes,
                    current.image_bytes,
                    old_mime_type=previous.mime_type,
                    new_mime_type=current.mime_type,
                )
                safe_comparison = self._guardrails.validate_model_response(comparison)
            except (GuardrailViolation, EmptyResponseError, AIClientError) as exc:
                logger.warning(
                    "Progress comparison fallback used: %s",
                    exc,
                    extra=log_extra(channel=channel, user_id=user_id, started_at=started_at),
                )
                safe_comparison = self._technical_pause_fallback()

            final_progress_reply = self._finalize_reply(
                response_mode,
                user_text,
                safe_comparison,
                session,
                has_photo=True,
                short_mode=tuning.short_mode,
                beginner_mode=tuning.beginner_mode,
                low_confidence=tuning.low_confidence,
                simple_question=tuning.simple_question,
                routine_request=tuning.routine_request,
            )
            self._memory.remember_assistant_message(user_id, final_progress_reply)
            self._store_recommendation(user_id, session, response_mode, final_progress_reply)
            return final_progress_reply

        history = self._token_guard.trim_history(self._memory.get_context_history(user_id), session)
        payload = [{"role": turn.role, "content": turn.content} for turn in history]

        prompt = build_system_prompt(
            response_mode,
            session,
            self._knowledge,
            runtime_guidance=tuning.runtime_guidance,
        )

        max_tokens, verbosity = self._response_profile(
            response_mode,
            user_text,
            safety,
            short_mode=tuning.short_mode,
            beginner_mode=tuning.beginner_mode,
        )

        try:
            raw_reply = await self._openai_client.generate_reply_with_image(
                system_prompt=prompt,
                dialogue=payload,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                image_caption=caption_text or "Проанализируйте фото лица и дайте рекомендации по уходу.",
                max_output_tokens=max_tokens,
                verbosity=verbosity,
            )
            safe_reply = self._guardrails.validate_model_response(raw_reply)
        except (GuardrailViolation, EmptyResponseError, AIClientError) as exc:
            logger.warning(
                "Model image fallback used: %s",
                exc,
                extra=log_extra(channel=channel, user_id=user_id, started_at=started_at),
            )
            safe_reply = self._technical_pause_fallback()

        final_reply = self._finalize_reply(
            response_mode,
            user_text,
            safe_reply,
            session,
            has_photo=True,
            short_mode=tuning.short_mode,
            beginner_mode=tuning.beginner_mode,
            low_confidence=tuning.low_confidence,
            simple_question=tuning.simple_question,
            routine_request=tuning.routine_request,
        )
        final_reply = self._apply_conversion(user_id, session, user_text, final_reply, channel)
        self._memory.remember_assistant_message(user_id, final_reply)
        self._store_recommendation(user_id, session, response_mode, final_reply)
        return final_reply

    def _mark_consultation_started(self, user_id: str, session: UserSession, channel: str) -> None:
        if session.consultation_started:
            return
        session.consultation_started = True
        self._save_crm_event(
            user_id,
            "consultation_started",
            {"channel": channel},
        )

    def _capture_profile_signals(self, user_id: str, session: UserSession, user_text: str, channel: str) -> None:
        lowered = user_text.lower()
        journal = session.skin_journal

        if any(token in lowered for token in self._PROBLEM_MARKERS):
            session.concerns = user_text.strip()
            self._save_crm_event(
                user_id,
                "problem_detected",
                {
                    "channel": channel,
                    "text": user_text,
                },
            )

        detected = self._extract_skin_type(lowered)
        if detected:
            session.skin_type = detected
            session.skin_type_confidence = max(session.skin_type_confidence or 0.0, 0.72)
            journal["skin_type"] = detected
            self._save_crm_event(
                user_id,
                "skin_type_detected",
                {
                    "channel": channel,
                    "skin_type": detected,
                    "confidence": session.skin_type_confidence,
                },
            )

        if "аллер" in lowered or "реакц" in lowered:
            session.allergies = user_text.strip()
            self._append_journal_item(journal, "reactions", session.allergies)

        if any(marker in lowered for marker in self._WORKED_MARKERS):
            self._append_journal_item(journal, "worked", user_text.strip())

        if any(marker in lowered for marker in self._NOT_WORKED_MARKERS):
            self._append_journal_item(journal, "not_worked", user_text.strip())

    def _resolve_response_mode(self, session: UserSession, user_text: str) -> ChatMode:
        lowered = user_text.lower()
        selected_mode = session.mode

        if any(marker in lowered for marker in self._INGREDIENT_MARKERS):
            session.mode = ChatMode.INGREDIENT_CHECK
            return ChatMode.INGREDIENT_CHECK

        if any(marker in lowered for marker in self._SKIN_TYPE_MARKERS):
            session.mode = ChatMode.SKIN_TYPE
            return ChatMode.SKIN_TYPE

        if any(marker in lowered for marker in self._PROBLEM_MARKERS):
            session.mode = ChatMode.PROBLEM_SOLVING
            return ChatMode.PROBLEM_SOLVING

        return selected_mode

    def _handle_menu_selection(self, user_id: str, text: str) -> str | None:
        lowered = " ".join(text.lower().split())

        if lowered in self._MENU_CONSULTATION_LABELS:
            self.set_mode(user_id, ChatMode.CONSULTATION)
            return "Отлично, начнём консультацию. Опишите, что хотите улучшить в уходе."

        if lowered in self._MENU_SKIN_TYPE_LABELS:
            self.set_mode(user_id, ChatMode.SKIN_TYPE)
            return "Хорошо, помогу определить тип кожи. Можете описать ощущения кожи или отправить фото без фильтров."

        if lowered in self._MENU_PROBLEM_LABELS:
            self.set_mode(user_id, ChatMode.PROBLEM_SOLVING)
            return "Давайте разберём проблему. Опишите, что беспокоит и как давно это проявляется."

        return None

    def _should_close_follow_up(self, session: UserSession, user_text: str) -> bool:
        if not is_simple_decline(user_text) or not session.history:
            return False

        last_assistant = next(
            (turn.content.lower() for turn in reversed(session.history) if turn.role == "assistant"),
            "",
        )
        return any(marker in last_assistant for marker in self._FOLLOW_UP_PROMPT_MARKERS)

    def _finalize_reply(
        self,
        mode: ChatMode,
        user_text: str,
        source_text: str,
        session: UserSession,
        *,
        has_photo: bool,
        short_mode: bool = False,
        beginner_mode: bool = False,
        low_confidence: bool = False,
        simple_question: bool = False,
        routine_request: bool = False,
    ) -> str:
        body = self._postprocess_content(source_text)
        body = self.simplify_language(body)
        if not has_photo and not session.progress_photos:
            body = self._strip_visual_claims_without_photo(body)
            body = self._enforce_non_assumptive_symptom_language(body, user_text, session)
            body = self._enforce_uncertainty_without_photo(body)
        body = self._remove_age_based_skin_claims(body)
        body = self._ensure_reaction(body, user_text, session, has_photo=has_photo)
        body = self._deescalate_when_user_doubts(body, user_text, has_photo=has_photo)
        body = self._remove_duplicate_reaction_lines(body)
        body = self._ensure_practical_action(body)
        # TEMP: не урезаем содержимое ответа для простых вопросов.
        # if simple_question and not routine_request:
        #     body = self._trim_unrequested_routine_sections(body, user_text)
        body = self._ensure_soft_closing(
            body,
            session,
            mode,
            user_text=user_text,
            short_mode=short_mode,
            low_confidence=low_confidence,
        )
        if self._asks_human_contact(user_text):
            body = self._append_human_contact_hint(body)
        if low_confidence:
            body = self._ensure_uncertainty_question(body)
        personalized = self._apply_personalization(body, session, user_text)
        personalized = self._strip_disallowed_gpt_style(personalized)
        # TEMP: отключены все пост-лимиты длины, чтобы не обрезать ответы.
        # personalized = self._enforce_telegram_compact_limits(personalized)
        # if short_mode:
        #     personalized = self._enforce_short_answer_mode(personalized)
        # if beginner_mode:
        #     personalized = self._enforce_beginner_compactness(personalized)
        personalized = self._sanitize_text_flow(personalized)
        personalized = self.humanizer_pipeline(personalized)
        personalized = self._ensure_key_highlights(personalized)
        personalized = self._enforce_bold_fragment_budget(personalized, max_fragments=3)
        personalized = self._ensure_message_emojis(personalized)
        personalized = self._enforce_emoji_budget(personalized, max_emojis=2)
        return clean_response(personalized, fallback=self._fallback_for_mode(mode))

    def _postprocess_content(self, text: str) -> str:
        normalized = text
        normalized = re.sub(r"\bбренд\b", "категорию средства", normalized, flags=re.IGNORECASE)
        return normalized.strip()

    def _ensure_reaction(self, text: str, user_text: str, session: UserSession, *, has_photo: bool) -> str:
        if not text.strip():
            return text

        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        lowered_first = first_line.lower()
        if any(lowered_first.startswith(marker) for marker in self._REACTION_STARTERS):
            return text

        intent = self._detect_user_intent(user_text)

        if self._is_doubt_or_objection(user_text):
            reaction = "Вы правы, без фото сложно оценить точно."
        elif has_photo:
            reaction = "Спасибо за фото, это помогает точнее оценить ситуацию."
        elif intent == "question":
            reaction = "Очень хороший вопрос."
        elif intent == "complaint":
            reaction = "Понимаю, это может быть неприятно."
        elif intent == "follow_up":
            reaction = "Отлично, продолжаем."
        elif any(marker in user_text.lower() for marker in self._PROBLEM_MARKERS):
            reaction = "Такое бывает довольно часто, Вы не одни с этим сталкиваетесь."
        else:
            reaction = "Понимаю Ваш запрос."

        previous_opening = self._last_assistant_opening(session)
        if previous_opening and previous_opening == reaction.lower():
            reaction = "Поняла Вас, давайте разберем спокойно и по шагам."

        return f"{reaction}\n\n{text.strip()}"

    def _ensure_practical_action(self, text: str) -> str:
        lowered = text.lower()
        if any(marker in lowered for marker in self._PRACTICAL_MARKERS):
            return text

        practical_line = (
            "Практически: начните с одного действия — добавьте ежедневный SPF, "
            "а новые активы вводите постепенно через патч-тест."
        )
        return f"{text.strip()}\n\n{practical_line}"

    def _ensure_soft_closing(
        self,
        text: str,
        session: UserSession,
        mode: ChatMode,
        *,
        user_text: str,
        short_mode: bool,
        low_confidence: bool,
    ) -> str:
        normalized = re.sub(
            r"(?i)\s+(если хотите|если нужно|если удобно|могу также|могу|подключу менеджера|передам диалог|при желании)\b",
            r"\n\1",
            text,
        )
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if not lines:
            return self._SOFT_CLOSINGS[0]

        content_lines: list[str] = []
        selected_closing: str | None = None

        for line in lines:
            matched_closing = next(
                (closing for closing in self._SOFT_CLOSINGS if line.lower() == closing.lower()),
                None,
            )
            if matched_closing is not None:
                if selected_closing is None:
                    selected_closing = matched_closing
                continue

            if self._is_cta_line(line):
                if selected_closing is None and session.purchase_stage == "hot_lead":
                    selected_closing = line
                continue

            content_lines.append(line)

        if selected_closing is None:
            selected_closing = self.ending_selector(
                session=session,
                mode=mode,
                user_text=user_text,
                short_mode=short_mode,
                low_confidence=low_confidence,
            )

        content = "\n\n".join(content_lines).strip()
        if not selected_closing:
            return content
        if not content:
            return selected_closing
        return f"{content}\n\n{selected_closing}"

    def ending_selector(
        self,
        *,
        session: UserSession,
        mode: ChatMode,
        user_text: str,
        short_mode: bool,
        low_confidence: bool,
    ) -> str | None:
        if session.purchase_stage == "hot_lead":
            return self._CONVERSION_CLOSINGS[0]
        if low_confidence:
            return "Если хотите, уточните 1–2 детали, и я подстрою рекомендацию точнее."
        if self._is_follow_up_short_reply(user_text):
            return "Продолжим с этого шага или лучше коротко сравнить варианты?"

        turn_index = max(session.total_messages_received, 1)
        if short_mode and turn_index % 3 == 0:
            return None
        if turn_index % 4 == 0:
            return None
        if mode in {ChatMode.INGREDIENT_CHECK, ChatMode.SKIN_TYPE}:
            return self._EDUCATIONAL_CLOSINGS[0]
        if turn_index % 2 == 0:
            return self._SUPPORT_CLOSINGS[0]
        return self._EDUCATIONAL_CLOSINGS[1]

    def _apply_personalization(self, text: str, session: UserSession, user_text: str) -> str:
        if not session.onboarding_completed or not session.name:
            return text

        if not self._should_use_name(session, user_text):
            return text

        name = session.name.strip()
        if not name:
            return text

        pattern = re.compile(re.escape(name), re.IGNORECASE)
        matches = list(pattern.finditer(text))
        if not matches:
            return f"{name}, {text}"

        if len(matches) == 1:
            return text

        first = matches[0]
        head = text[: first.end()]
        tail = text[first.end() :]
        tail = pattern.sub("", tail)
        tail = re.sub(r"\s{2,}", " ", tail)
        return (head + tail).strip()

    def _should_use_name(self, session: UserSession, user_text: str) -> bool:
        if not session.name:
            return False
        lowered = user_text.lower().strip()
        if lowered in {"ок", "окей", "спасибо", "понял", "поняла"}:
            return False
        if self._is_doubt_or_objection(user_text):
            return True
        return session.total_messages_received <= 2 or session.total_messages_received % 5 == 0

    def _apply_conversion(
        self,
        user_id: str,
        session: UserSession,
        user_text: str,
        response_text: str,
        channel: str,
    ) -> str:
        if not self._has_explicit_purchase_intent(user_text):
            return response_text

        user_message_count = self._memory.count_user_messages(user_id)
        has_intent = self._conversion_engine.detect_purchase_intent(
            user_text,
            user_message_count=user_message_count,
        )
        if not has_intent:
            return response_text

        if not self._conversion_engine.is_hot_lead(session):
            session.purchase_stage = "hot_lead"
            try:
                self._crm.mark_hot_lead(user_id)
            except Exception as exc:
                logger.warning("CRM hot lead mark failed: %s", exc)

            self._save_crm_event(
                user_id,
                "purchase_intent",
                {
                    "channel": channel,
                    "user_text": user_text,
                    "message_count": user_message_count,
                },
            )

        soft_offer = self._conversion_engine.build_soft_offer().strip()
        human_handoff = self._conversion_engine.escalate_to_human().strip()
        offer_block = " ".join(part for part in (soft_offer, human_handoff) if part).strip()
        if not offer_block:
            return response_text

        core = self._strip_soft_closing_tail(response_text)
        if not core:
            return offer_block
        return f"{core}\n\n{offer_block}"

    def _response_profile(
        self,
        mode: ChatMode,
        user_text: str,
        guard_decision: InputGuardDecision,
        *,
        short_mode: bool = False,
        beginner_mode: bool = False,
    ) -> tuple[int, str]:
        complexity = self._complexity_level(user_text)
        if complexity == "simple":
            tokens = 900
            verbosity = "low"
        elif complexity == "medium":
            tokens = 1200
            verbosity = "low"
        else:
            tokens = 1600
            verbosity = "medium"
        # TEMP: режимы не должны дополнительно ужимать длину генерации.
        # if mode == ChatMode.INGREDIENT_CHECK:
        #     tokens = min(tokens, 360)
        #
        # if short_mode:
        #     tokens = min(tokens, 220)
        #     verbosity = "low"
        #
        # if beginner_mode:
        #     tokens = min(tokens, 260)

        tokens = int(tokens * guard_decision.token_multiplier)
        tokens = max(tokens, 700)

        if guard_decision.forced_verbosity:
            verbosity = guard_decision.forced_verbosity

        return tokens, verbosity

    def _complexity_level(self, user_text: str) -> str:
        lowered = user_text.lower()
        problem_hits = sum(1 for marker in self._PROBLEM_MARKERS if marker in lowered)
        if len(user_text) > 100 or "сравни" in lowered or problem_hits >= 2:
            return "complex"
        if len(user_text) > 55:
            return "medium"
        return "simple"

    def _build_response_tuning(
        self,
        *,
        session: UserSession,
        user_text: str,
        source_user_text: str,
        mode: ChatMode,
        has_photo: bool,
    ) -> ResponseTuning:
        signals = self._context_intelligence.analyze(user_text, mode)
        lines = [self._context_intelligence.build_runtime_guidance(signals, mode)]

        beginner_mode = self._is_beginner_mode(user_text, session)
        simple_question = self._is_simple_question(user_text)
        short_mode = self._is_short_answer_mode(user_text, session)
        routine_request = self._is_routine_builder_request(user_text)
        user_intent = self._detect_user_intent(source_user_text)
        low_confidence = self._is_low_confidence_answer(
            user_text=user_text,
            session=session,
            has_photo=has_photo,
        )

        lines.append(f"Intent: {user_intent}.")

        if self._is_doubt_or_objection(user_text):
            lines.append(
                "Пользователь сомневается: не спорьте, признавайте ограничения данных, предложите уточнение."
            )

        if source_user_text != user_text:
            lines.append(
                "Короткая реплика привязана к прошлому контексту. Продолжайте тему, не начинайте заново."
            )

        if self._is_follow_up_short_reply(source_user_text):
            lines.append("Это follow-up: ответ коротко, по делу, без лекции.")

        if not has_photo:
            lines.append(
                "Фото нет: не делайте визуальных выводов, опирайтесь только на описание пользователя."
            )
        else:
            lines.append("Фото есть: используйте мягкие визуальные оценки без категоричности.")

        if beginner_mode:
            lines.append("Новичок: максимум 3 шага, простой язык, мягкий тон.")

        if simple_question:
            lines.append("Вопрос простой: ответ короткий, без длинных схем и списков.")

        if short_mode:
            lines.append("Short mode: 4-6 строк, одна мысль на абзац.")

        if routine_request:
            lines.append("Соберите уход в 1 экран: Утро / Вечер / Раз в неделю. Коротко и по сути.")
        else:
            lines.append("Не используйте формат «Утро/Вечер», если пользователь не просил.")

        if self._is_progress_follow_up(user_text):
            lines.append("Follow-up по динамике: кратко, как в чате, с ближайшим чекпоинтом.")

        if self._is_ingredient_explainer_request(user_text):
            lines.append("Ингредиент: объясните в 2 строки (польза + риск/ограничение).")

        lines.append("Ответ должен ощущаться как сообщение в мессенджере, не статья.")
        lines.append("Короткие абзацы для мобильного экрана.")
        lines.append("Лучше честность, чем уверенность без данных.")

        if mode != ChatMode.INGREDIENT_CHECK and (beginner_mode or not short_mode or user_intent == "follow_up"):
            lines.append("enable_soft_closing=True")

        if low_confidence:
            lines.append("Сначала обозначьте неопределенность и задайте 1 уточняющий вопрос.")
            lines.append("confidence=low")
        else:
            lines.append("confidence=high")

        runtime_guidance = self._compact_runtime_guidance(lines)
        return ResponseTuning(
            runtime_guidance=runtime_guidance,
            short_mode=short_mode,
            beginner_mode=beginner_mode,
            low_confidence=low_confidence,
            simple_question=simple_question,
            routine_request=routine_request,
        )

    @staticmethod
    def _compact_runtime_guidance(lines: list[str], *, max_lines: int = 10, max_chars: int = 900) -> str:
        compacted: list[str] = []
        control_lines: list[str] = []
        seen: set[str] = set()
        for raw_line in lines:
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue
            if line.startswith(("confidence=", "enable_soft_closing=")):
                control_lines.append(line)
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            compacted.append(line)
            if len(compacted) >= max_lines:
                break

        guidance = "\n".join([*compacted, *control_lines]).strip()
        if len(guidance) > max_chars:
            guidance = guidance[:max_chars].rstrip(" ,;:")
        return guidance

    def _store_recommendation(self, user_id: str, session: UserSession, mode: ChatMode, reply: str) -> None:
        lines = [line.strip("•- ") for line in reply.splitlines() if line.strip()]
        session.last_recommendations = lines[-3:]
        self._save_crm_event(
            user_id,
            "recommendation_given",
            {
                "mode": mode.value,
                "preview": reply[:300],
            },
        )

    def _save_crm_event(self, user_id: str, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._crm.save_event(user_id, event_type, payload)
        except NotImplementedError:
            return
        except Exception as exc:
            logger.warning("CRM event save failed: %s", exc)
            return

    @staticmethod
    def _append_journal_item(journal: dict[str, Any], key: str, value: str | None) -> None:
        if not value:
            return
        normalized = " ".join(value.split()).strip()
        if not normalized:
            return
        bucket = journal.setdefault(key, [])
        if not isinstance(bucket, list):
            journal[key] = [normalized[:120]]
            return
        if normalized in bucket:
            return
        bucket.append(normalized[:120])
        if len(bucket) > 8:
            del bucket[:-8]

    @classmethod
    def _extract_skin_type(cls, lowered_text: str) -> str | None:
        if "комбинир" in lowered_text:
            return "комбинированная"
        if "жирн" in lowered_text:
            return "жирная"
        if "сух" in lowered_text:
            return "сухая"
        if "чувств" in lowered_text:
            return "чувствительная"
        if "нормаль" in lowered_text:
            return "нормальная"
        return None

    def simplify_language(self, text: str) -> str:
        simplified = text.strip()
        if not simplified:
            return simplified

        technical_detected = self._has_technical_info(simplified)
        formal_detected = self._is_formal_tone(simplified)
        simplified = self._replace_complex_terms(simplified)
        simplified = self._remove_over_academic_structures(simplified)
        # TEMP: не сокращаем список активов в готовом ответе.
        # simplified = self._limit_active_mentions(simplified, max_active=3)
        simplified = self._split_long_sentences(simplified, max_words=18)
        if technical_detected:
            simplified = self._inject_human_translator_line(simplified)
        simplified = self._inject_warmth_if_formal(simplified, force=formal_detected)
        # TEMP: не ограничиваем число абзацев, чтобы не терять хвост ответа.
        # simplified = self._enforce_conversational_rhythm(simplified, max_paragraphs=8)
        simplified = self._bold_ingredients(simplified)
        simplified = re.sub(r"\n{3,}", "\n\n", simplified)
        return simplified.strip()

    @classmethod
    def _replace_complex_terms(cls, text: str) -> str:
        simplified = text
        for source, target in cls._MEDICAL_TO_SIMPLE:
            simplified = re.sub(re.escape(source), target, simplified, flags=re.IGNORECASE)
        simplified = re.sub(r"(?i)\bвызывает\s+потеря\s+влаги\b", "из-за этого кожа теряет влагу", simplified)
        simplified = re.sub(r"(?i)\bприводит\s+к\s+потеря\s+влаги\b", "из-за этого кожа теряет влагу", simplified)
        simplified = re.sub(
            r"(?i)ослабленный защитный слой кожи из-за этого кожа теряет влагу",
            "Если защитный слой кожи ослаблен, она быстрее теряет влагу",
            simplified,
        )

        simplified = re.sub(r"(?i)\bкомедонолитический\b", "против черных точек", simplified)
        simplified = re.sub(r"(?i)\bпредпочтительно\b", "лучше", simplified)
        simplified = re.sub(r"(?i)\bрекомендуется\b", "лучше", simplified)
        simplified = re.sub(r"(?i)\bцелесообразно\b", "лучше", simplified)
        simplified = re.sub(r"(?i)\bнеобходимо\b", "важно", simplified)
        simplified = re.sub(r"(?i)\bследует\b", "лучше", simplified)
        return simplified

    @staticmethod
    def _remove_over_academic_structures(text: str) -> str:
        simplified = re.sub(r"(?i)\bв\s+рамках\b", "", text)
        simplified = re.sub(r"(?i)\bданный\b", "", simplified)
        simplified = re.sub(r"(?i)\b(?:следует|лучше)\s+отметить[,:\s]*", "", simplified)
        simplified = re.sub(r"(?i)\bчто\s+подход\b", "подход", simplified)
        simplified = re.sub(r"\s{2,}", " ", simplified)
        simplified = re.sub(r"\s+([,.;:!?])", r"\1", simplified)
        return simplified.strip()

    @staticmethod
    def _split_long_sentences(text: str, max_words: int = 18) -> str:
        chunks = re.split(r"(?<=[.!?])\s+", text.strip())
        rebuilt: list[str] = []
        for chunk in chunks:
            sentence = chunk.strip()
            if not sentence:
                continue
            words = sentence.split()
            if len(words) <= max_words:
                rebuilt.append(sentence)
                continue

            split_index = max(8, min(len(words) - 1, max_words // 2 + 2))
            first = " ".join(words[:split_index]).rstrip(",;:")
            second = " ".join(words[split_index:]).strip()
            if first and first[-1] not in ".!?":
                first = f"{first}."
            if second and second[0].islower():
                second = f"{second[0].upper()}{second[1:]}"

            rebuilt.append(first)
            if second:
                rebuilt.append(second)

        return " ".join(rebuilt).strip()

    @classmethod
    def _limit_active_mentions(cls, text: str, max_active: int = 3) -> str:
        lowered = text.lower()
        mentioned = [
            active
            for active in cls._ACTIVE_INGREDIENTS
            if re.search(rf"\b{re.escape(active)}\b", lowered, flags=re.IGNORECASE)
        ]
        if len(mentioned) <= max_active:
            return text

        keep: list[str] = [active for active in cls._ACTIVE_PRIORITY if active in mentioned]
        keep = keep[:max_active]
        for active in mentioned:
            if active not in keep:
                keep.append(active)
            if len(keep) >= max_active:
                break

        dropped = [active for active in mentioned if active not in keep]
        limited = text
        for active in dropped:
            limited = re.sub(rf"\b{re.escape(active)}\b", "", limited, flags=re.IGNORECASE)

        limited = re.sub(r"\s*,\s*,+", ", ", limited)
        limited = re.sub(r"(?i)\b(и|или)\s*(?=[,.;!?])", "", limited)
        limited = re.sub(r",\s*(?:,|\.)", ".", limited)
        limited = re.sub(r"\(\s*\)", "", limited)
        limited = re.sub(r"\s{2,}", " ", limited).strip()
        limited = re.sub(r"[,\s]+([.!?])", r"\1", limited)
        limited = re.sub(r"\s{2,}", " ", limited).strip()
        if "2–3 актив" not in limited.lower():
            limited = f"{limited}\n\nЛучше начать с 2–3 активов и смотреть на реакцию кожи."
        return limited

    @classmethod
    def _has_technical_info(cls, text: str) -> bool:
        lowered = text.lower()
        if any(marker in lowered for marker in cls._PLAIN_TECH_MARKERS):
            return True
        return any(source in lowered for source, _ in cls._MEDICAL_TO_SIMPLE)

    @staticmethod
    def _inject_human_translator_line(text: str) -> str:
        lowered = text.lower()
        if "проще говоря:" in lowered or "если совсем просто:" in lowered:
            return text

        if any(marker in lowered for marker in ("сух", "потеря влаги", "обезвож")):
            translator = "Проще говоря: коже не хватает увлажнения."
        else:
            translator = "Если совсем просто: коже нужен более мягкий и понятный уход."

        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs:
            return translator
        insert_at = 1 if len(paragraphs) > 1 else len(paragraphs)
        paragraphs.insert(insert_at, translator)
        return "\n\n".join(paragraphs).strip()

    @staticmethod
    def _inject_warmth_if_formal(text: str, *, force: bool = False) -> str:
        lowered = text.lower()
        if "если говорить проще," in lowered or "если по-человечески," in lowered:
            return text

        formal_markers = ("рекомендуется", "необходимо", "следует", "целесообразно", "в рамках", "данный")
        if not force and sum(marker in lowered for marker in formal_markers) < 2:
            return text

        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs:
            return text
        paragraphs.insert(0, "Если говорить проще,")
        return "\n\n".join(paragraphs).strip()

    @staticmethod
    def _is_formal_tone(text: str) -> bool:
        lowered = text.lower()
        formal_markers = ("рекомендуется", "необходимо", "следует", "целесообразно", "в рамках", "данный")
        return sum(marker in lowered for marker in formal_markers) >= 2

    @staticmethod
    def _enforce_conversational_rhythm(text: str, max_paragraphs: int = 8) -> str:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
        if not sentences:
            return text.strip()

        paragraphs: list[str] = []
        for sentence in sentences:
            if (
                paragraphs
                and len(paragraphs[-1].split()) <= 5
                and len(sentence.split()) <= 9
                and not paragraphs[-1].endswith(":")
            ):
                paragraphs[-1] = f"{paragraphs[-1]} {sentence}"
            else:
                paragraphs.append(sentence)

        return "\n\n".join(paragraphs[:max_paragraphs]).strip()

    @classmethod
    def _bold_ingredients(cls, text: str) -> str:
        formatted = text
        highlighted = 0
        for ingredient in cls._ACTIVE_INGREDIENTS:
            pattern = re.compile(rf"\b({re.escape(ingredient)})\b", re.IGNORECASE)
            if pattern.search(formatted):
                formatted = pattern.sub(lambda m: f"*{m.group(1)}*", formatted, count=1)
                highlighted += 1
                if highlighted >= 2:
                    break
        return formatted

    @staticmethod
    def _is_progress_request(user_text: str) -> bool:
        lowered = user_text.lower()
        return "сравни" in lowered or "прогресс" in lowered or "динамик" in lowered

    @staticmethod
    def _is_theoretical_question(user_text: str) -> bool:
        lowered = user_text.lower()
        markers = (
            "можно ли",
            "как работает",
            "почему",
            "стоит ли",
            "ретинол",
            "spf",
        )
        return "?" in user_text or any(marker in lowered for marker in markers)

    def _detect_user_intent(self, user_text: str) -> str:
        lowered = user_text.lower().strip()
        if self._is_follow_up_short_reply(user_text):
            return "follow_up"
        if self._is_theoretical_question(user_text):
            return "question"
        if any(marker in lowered for marker in self._COMPLAINT_MARKERS):
            return "complaint"
        return "statement"

    def _asks_human_contact(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(marker in lowered for marker in self._HUMAN_CONTACT_MARKERS)

    def _append_human_contact_hint(self, text: str) -> str:
        hint = self._conversion_engine.escalate_to_human().strip()
        if not hint:
            return text
        if hint.lower() in text.lower():
            return text
        return f"{text.strip()}\n\n{hint}"

    def _is_strict_domain_offtopic(self, user_text: str) -> bool:
        lowered = user_text.lower()
        if any(marker in lowered for marker in self._DOMAIN_KEYWORDS):
            return False
        return any(marker in lowered for marker in self._OFFTOPIC_MARKERS)

    @staticmethod
    def _soft_domain_redirect(user_text: str, fallback: str | None = None) -> str:
        _ = user_text
        if fallback:
            return (
                f"{fallback}\n\n"
                "Если хотите, давайте вернемся к коже: могу помочь с типом кожи, "
                "проблемой или составом средства 🤍"
            )
        return (
            "Я сфокусирована на коже и уходе 🤍\n\n"
            "Если хотите, давайте разберем Ваш запрос по типу кожи, проблеме или составу средства."
        )

    def _smooth_user_intent(self, user_text: str, session: UserSession) -> str:
        text = " ".join(user_text.split())
        if not self._is_follow_up_short_reply(text):
            return text

        recent_user = next(
            (
                turn.content.strip()
                for turn in reversed(session.history)
                if turn.role == "user" and turn.content.strip()
            ),
            "",
        )
        if recent_user:
            return f"{recent_user}. Уточнение пользователя: {text}"

        recent_assistant = next(
            (
                turn.content.strip()
                for turn in reversed(session.history)
                if turn.role == "assistant" and turn.content.strip()
            ),
            "",
        )
        if recent_assistant:
            return f"Контекст диалога: {recent_assistant[:160]}. Уточнение пользователя: {text}"
        return text

    def _is_follow_up_short_reply(self, user_text: str) -> bool:
        lowered = user_text.lower().strip()
        if len(lowered) > 24:
            return False
        if lowered in self._FOLLOW_UP_SHORT_MARKERS:
            return True
        return any(lowered.startswith(marker) for marker in self._FOLLOW_UP_SHORT_MARKERS)

    def _is_beginner_mode(self, user_text: str, session: UserSession) -> bool:
        lowered = user_text.lower()
        if any(marker in lowered for marker in self._BEGINNER_MARKERS):
            return True
        return not bool(session.last_recommendations)

    @staticmethod
    def _is_simple_question(user_text: str) -> bool:
        return len(user_text.strip()) < 80

    def _is_short_answer_mode(self, user_text: str, session: UserSession) -> bool:
        short_user_text = len(user_text.strip()) < 80
        many_messages = session.total_messages_received >= 8
        fast_dialogue = False
        if len(session.message_timestamps) >= 4:
            last_four = list(session.message_timestamps)[-4:]
            fast_dialogue = (last_four[-1] - last_four[0]) <= 45
        return short_user_text or many_messages or fast_dialogue

    def _is_routine_builder_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(marker in lowered for marker in self._ROUTINE_REQUEST_MARKERS)

    def _is_progress_follow_up(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(marker in lowered for marker in self._PROGRESS_FOLLOW_UP_MARKERS)

    def _has_symptom_description(self, user_text: str, session: UserSession) -> bool:
        context = self._build_user_symptom_context(user_text, session)
        mentioned = self._mentioned_symptom_groups(context)
        return bool(mentioned - {"appearance"})

    def _is_low_confidence_answer(self, *, user_text: str, session: UserSession, has_photo: bool) -> bool:
        if has_photo:
            return False
        if self._has_symptom_description(user_text, session):
            return False
        lowered = user_text.lower()
        return self._is_doubt_or_objection(user_text) or any(
            marker in lowered for marker in self._AMBIGUOUS_MARKERS
        )

    def _is_ingredient_explainer_request(self, user_text: str) -> bool:
        lowered = user_text.lower()
        matched = sum(1 for ingredient in self._ACTIVE_INGREDIENTS if ingredient in lowered)
        return matched == 1 and len(user_text.strip()) <= 90

    @staticmethod
    def _strip_visual_claims_without_photo(text: str) -> str:
        sanitized = text
        sentence_leads = (
            r"(?im)^\s*кожа выглядит достаточно спокойной\s*(?:[,:;.!?-]+\s*)?",
            r"(?im)^\s*в целом состояние кожи выглядит стабильным\s*(?:[,:;.!?-]+\s*)?",
            r"(?im)^\s*видно,\s*что кожа не перегружена уходом\s*(?:[,:;.!?-]+\s*)?",
            r"(?im)^\s*барьер кожи в хорошем состоянии\s*(?:[,:;.!?-]+\s*)?",
        )
        for pattern in sentence_leads:
            sanitized = re.sub(pattern, "", sanitized)

        visual_fragments = (
            r"(?i)\bкожа выглядит[^.!?\n]*(?:[.!?]|$)",
            r"(?i)(?:судя по фото|на фото видно|по фото видно)[^.!?\n]*(?:[.!?]|$)",
        )
        for pattern in visual_fragments:
            sanitized = re.sub(pattern, "", sanitized)

        sanitized = re.sub(r"^\s*и,\s*", "", sanitized, count=1, flags=re.IGNORECASE)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        sanitized = sanitized.strip()
        if sanitized and sanitized[0].islower():
            sanitized = f"{sanitized[0].upper()}{sanitized[1:]}"
        return sanitized

    @classmethod
    def _enforce_non_assumptive_symptom_language(
        cls,
        text: str,
        user_text: str,
        session: UserSession,
    ) -> str:
        context = cls._build_user_symptom_context(user_text, session)
        mentioned = cls._mentioned_symptom_groups(context)

        sanitized = text
        if not mentioned:
            sanitized = re.sub(
                r"(?i)\bсудя по описани[юя](?:\s+клиента)?\b",
                "В такой ситуации",
                sanitized,
            )

        lines = sanitized.splitlines()
        rewritten: list[str] = []
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                rewritten.append("")
                continue

            lowered = line.lower()
            if any(marker in lowered for marker in cls._HEDGE_MARKERS):
                rewritten.append(line)
                continue

            replaced_line = line
            for group, markers in cls._SYMPTOM_MARKERS.items():
                if group in mentioned:
                    continue
                if any(marker in lowered for marker in markers):
                    replaced_line = cls._SYMPTOM_SOFT_LINES[group]
                    break
            rewritten.append(replaced_line)

        sanitized = "\n".join(rewritten)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        return sanitized.strip()

    @classmethod
    def _enforce_uncertainty_without_photo(cls, text: str) -> str:
        sanitized = text

        type_pattern = re.compile(
            r"(?i)\bтип кожи(?:\s+по описанию)?\s*[:\-]\s*"
            r"(сух\w+|жир\w+|комбинирован\w+|чувствител\w+|нормаль\w+)"
        )
        sanitized = type_pattern.sub(
            lambda match: (
                f"По описанию это может быть {match.group(1)} кожа, "
                "но без фото и уточнений точно сказать сложно."
            ),
            sanitized,
        )

        strong_claim_pattern = re.compile(
            r"(?i)\bу вас\s+(сух\w+|жир\w+|комбинирован\w+|чувствител\w+|нормаль\w+)\s+кожа\b"
        )
        sanitized = strong_claim_pattern.sub(
            lambda match: (
                f"По описанию это может быть {match.group(1)} кожа, "
                "но лучше уточнить детали или фото."
            ),
            sanitized,
        )

        if "тип кожи" in sanitized.lower() and not any(
            marker in sanitized.lower() for marker in cls._UNCERTAINTY_MARKERS
        ):
            sanitized = f"{sanitized.strip()}\n\nВозможно, точнее скажу после уточнений или фото."

        sanitized = re.sub(r"\.{2,}", ".", sanitized)
        return sanitized.strip()

    @classmethod
    def _remove_age_based_skin_claims(cls, text: str) -> str:
        sanitized = text
        age_based_patterns = (
            r"(?i)\bв вашем возрасте\b[^.!?\n]*(?:[.!?]|$)",
            r"(?i)\bиз-за возраста\b[^.!?\n]*(?:[.!?]|$)",
            r"(?i)\bпо возрасту\b[^.!?\n]*(?:[.!?]|$)",
        )
        for pattern in age_based_patterns:
            sanitized = re.sub(pattern, "", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        return sanitized.strip()

    def _deescalate_when_user_doubts(self, text: str, user_text: str, *, has_photo: bool) -> str:
        if not self._is_doubt_or_objection(user_text):
            return text

        softened = re.sub(
            r"(?i)\b(однозначно|абсолютно|без сомнений)\b",
            "возможно",
            text,
        )
        if has_photo:
            return softened

        if "без фото сложно оценить точно" in softened.lower():
            return softened
        return f"Вы правы, без фото сложно оценить точно.\n\n{softened.strip()}"

    @classmethod
    def _build_user_symptom_context(cls, user_text: str, session: UserSession) -> str:
        recent_user_messages = [
            turn.content
            for turn in session.history
            if turn.role == "user" and turn.content.strip()
        ][-4:]
        parts = [user_text, session.concerns or "", *recent_user_messages]
        return " ".join(part for part in parts if part).lower()

    @classmethod
    def _mentioned_symptom_groups(cls, text: str) -> set[str]:
        mentioned: set[str] = set()
        for group, markers in cls._SYMPTOM_MARKERS.items():
            if any(marker in text for marker in markers):
                mentioned.add(group)
        return mentioned

    @staticmethod
    def _strip_disallowed_gpt_style(text: str) -> str:
        sanitized = text
        sanitized = re.sub(r"(?im)^\s*основной ответ\s*[:\-]?\s*$", "", sanitized)
        sanitized = re.sub(
            r"(?i)\bактивы\s+которые\s+рекомендую\b",
            "Подходящие активы",
            sanitized,
        )
        sanitized = re.sub(
            r"(?i)\bвероятный\s+тип(?:\s+кожи)?\b",
            "Тип кожи по описанию",
            sanitized,
        )
        sanitized = re.sub(r"(?i)\bосновной ответ\b\s*:?", "", sanitized)

        sanitized = re.sub(r"^\s*[-•]\s*", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
        sanitized = re.sub(r"(?im)^[,;:.!\-]+\s*", "", sanitized)
        return sanitized.strip()

    @staticmethod
    def _enforce_telegram_compact_limits(text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text.strip()

        unique_lines: list[str] = []
        seen_keys: set[str] = set()
        for raw_line in lines:
            line = re.sub(r"^\s*[-•]\s*", "", raw_line).strip()
            normalized_key = re.sub(r"[^\wа-яА-ЯёЁ]+", " ", line.lower()).strip()
            if normalized_key in {"и", "а", "но", "или"}:
                continue
            if normalized_key and normalized_key in seen_keys:
                continue
            if normalized_key:
                seen_keys.add(normalized_key)
            unique_lines.append(line)
            if len(unique_lines) >= 8:
                break

        limited_lines: list[str] = []
        word_budget = 120
        for line in unique_lines:
            words = line.split()
            if not words:
                continue
            if word_budget <= 0:
                break
            if len(words) <= word_budget:
                limited_lines.append(line)
                word_budget -= len(words)
                continue

            clipped = " ".join(words[:word_budget]).rstrip(" ,;:")
            if clipped:
                limited_lines.append(f"{clipped}…")
            break

        return "\n\n".join(limited_lines).strip()

    @staticmethod
    def _sanitize_text_flow(text: str) -> str:
        raw_lines = [line.rstrip() for line in text.splitlines()]
        filtered: list[str] = []
        for line in raw_lines:
            stripped = line.strip()
            if not stripped:
                if filtered and filtered[-1] != "":
                    filtered.append("")
                continue
            if re.fullmatch(r"[—\-•,;:.!?]+", stripped):
                continue
            if stripped.lower() in {"и", "а", "но", "или"}:
                continue
            filtered.append(stripped)

        stitched: list[str] = []
        for line in filtered:
            if not stitched:
                stitched.append(line)
                continue
            if line == "":
                if stitched[-1] != "":
                    stitched.append("")
                continue

            prev = stitched[-1]
            if prev and prev != "" and prev[-1] not in ".!?:;" and line[0].islower():
                stitched[-1] = f"{prev} {line}"
                continue
            stitched.append(line)

        deduped: list[str] = []
        for line in stitched:
            key = re.sub(r"\s+", " ", line.lower()).strip()
            if deduped and key and key == re.sub(r"\s+", " ", deduped[-1].lower()).strip():
                continue
            deduped.append(line)

        while deduped and not deduped[0].strip():
            deduped.pop(0)
        while deduped and not deduped[-1].strip():
            deduped.pop()

        return "\n".join(deduped).strip()

    def _remove_duplicate_reaction_lines(self, text: str) -> str:
        lines = text.splitlines()
        cleaned: list[str] = []
        prev_reaction = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if cleaned and cleaned[-1] != "":
                    cleaned.append("")
                prev_reaction = False
                continue
            is_reaction = self._is_reaction_line(stripped)
            if is_reaction and prev_reaction:
                continue
            cleaned.append(stripped)
            prev_reaction = is_reaction
        return "\n".join(cleaned).strip()

    def _trim_unrequested_routine_sections(self, text: str, user_text: str) -> str:
        if self._is_routine_builder_request(user_text):
            return text
        if not self._is_simple_question(user_text):
            return text

        sanitized = re.sub(r"(?im)^\s*(утро|вечер|раз в неделю)\s*[:\-].*$", "", text)
        sanitized = re.sub(r"(?m)^.*\|.*$", "", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        return sanitized.strip()

    @staticmethod
    def _ensure_uncertainty_question(text: str) -> str:
        lowered = text.lower()
        if "?" in text or "уточн" in lowered or "опишите" in lowered or "фото" in lowered:
            return text
        follow_up = "Если хотите, уточните ощущения после умывания или отправьте фото при дневном свете."
        return f"{text.strip()}\n\n{follow_up}"

    @staticmethod
    def _enforce_short_answer_mode(text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text.strip()

        limited_lines = lines[:6]
        if len(limited_lines) >= 2 and len(limited_lines[-1].split()) <= 2:
            limited_lines = limited_lines[:-1]
        return "\n\n".join(limited_lines).strip()

    @staticmethod
    def _enforce_beginner_compactness(text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text.strip()

        kept: list[str] = []
        step_count = 0
        for line in lines:
            is_step = bool(re.match(r"^\s*(\d+[\).]|[-•])\s*", line))
            if is_step:
                step_count += 1
                if step_count > 3:
                    continue
            kept.append(line)
        return "\n\n".join(kept).strip()

    @staticmethod
    def _merge_short_paragraphs(text: str) -> str:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs:
            return text.strip()

        merged: list[str] = []
        for paragraph in paragraphs:
            if (
                merged
                and len(merged[-1].split()) <= 4
                and len(paragraph.split()) <= 10
                and not merged[-1].endswith(":")
            ):
                merged[-1] = f"{merged[-1]} {paragraph}"
            else:
                merged.append(paragraph)
        return "\n\n".join(merged).strip()

    @staticmethod
    def _fix_ragged_ending(text: str) -> str:
        if not text.strip():
            return text.strip()
        trimmed = text.rstrip()
        trimmed = re.sub(r"(?:\s+(и|а|но|или))\s*$", "", trimmed, flags=re.IGNORECASE)
        trimmed = re.sub(r"[,:;]+$", ".", trimmed)
        return trimmed.strip()

    def humanizer_pipeline(self, reply: str) -> str:
        humanized = self._soften_bureaucratic_tone(reply)
        humanized = self._strip_ai_scaffold(humanized)
        humanized = self._repair_broken_word_chunks(humanized)
        humanized = self._rewrite_contact_refusal(humanized)
        humanized = self._remove_duplicate_reaction_lines(humanized)
        humanized = self._merge_short_paragraphs(humanized)
        humanized = self._self_rewrite_if_needed(humanized)
        humanized = self._fix_ragged_ending(humanized)
        return humanized.strip()

    def _soften_bureaucratic_tone(self, text: str) -> str:
        softened = text
        for pattern, replacement in self._BUREAUCRATIC_PATTERNS:
            softened = pattern.sub(replacement, softened)
        return softened

    @staticmethod
    def _strip_ai_scaffold(text: str) -> str:
        sanitized = text
        sanitized = re.sub(r"(?im)^\s*(итог|вывод|резюме)\s*:\s*", "", sanitized)
        sanitized = re.sub(r"(?im)^\s*(шаг\s*\d+|пункт\s*\d+)\s*:\s*", "", sanitized)
        sanitized = re.sub(r"(?im)^\s*в рамках запроса[,:\s]*", "", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        return sanitized.strip()

    def _self_rewrite_if_needed(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text.strip()

        formal_hits = sum(
            1
            for line in lines
            if any(word in line.lower() for word in ("рекомендуется", "необходимо", "следует", "целесообразно"))
        )
        if formal_hits >= 2:
            rewritten = [line for line in lines if not re.match(r"(?i)^(во-?первых|во-?вторых|в-третьих)\b", line)]
            return "\n\n".join(rewritten).strip()
        return "\n\n".join(lines).strip()

    @staticmethod
    def _repair_broken_word_chunks(text: str) -> str:
        repaired = text
        # Join accidental line breaks inside words: "панте\nнолом" -> "пантенолом"
        repaired = re.sub(r"(?iu)(\*?[а-яa-z]{3,})\n([а-яa-z]{2,}\*?)", r"\1\2", repaired)
        repaired = re.sub(r"(?iu)(\*?[а-яa-z]{3,})\s+\n\s+([а-яa-z]{2,}\*?)", r"\1\2", repaired)
        repaired = re.sub(r"\n{3,}", "\n\n", repaired)
        return repaired

    def _rewrite_contact_refusal(self, text: str) -> str:
        normalized = text
        refusal_pattern = re.compile(r"(?i)я\s+не\s+даю\s+прямых\s+контактов[^.!?\n]*(?:[.!?]|$)")
        if refusal_pattern.search(normalized):
            handoff = self._conversion_engine.escalate_to_human().strip()
            normalized = refusal_pattern.sub(f"{handoff} ", normalized)
            normalized = re.sub(r"\s{2,}", " ", normalized)
        return normalized.strip()

    @staticmethod
    def _enforce_bold_fragment_budget(text: str, max_fragments: int = 3) -> str:
        pattern = re.compile(r"\*([^*\n]+)\*")
        matches = list(pattern.finditer(text))
        if len(matches) <= max_fragments:
            return text

        seen = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal seen
            if seen < max_fragments:
                seen += 1
                return match.group(0)
            return match.group(1)

        return pattern.sub(_replace, text)

    @classmethod
    def _ensure_key_highlights(cls, text: str) -> str:
        highlighted = cls._count_bold_fragments(text)
        if highlighted >= 3:
            return text

        emphasized = text
        patterns = (
            re.compile(r"(?<!\*)\bspf\b(?!\*)", re.IGNORECASE),
            re.compile(r"(?<!\*)\bпатч-тест\b(?!\*)", re.IGNORECASE),
            re.compile(r"(?<!\*)\bувлажняющий крем\b(?!\*)", re.IGNORECASE),
            re.compile(r"(?<!\*)\bмягкое очищение\b(?!\*)", re.IGNORECASE),
        )
        for pattern in patterns:
            if highlighted >= 3:
                break
            if pattern.search(emphasized):
                emphasized = pattern.sub(lambda m: f"*{m.group(0)}*", emphasized, count=1)
                highlighted += 1

        return emphasized

    @classmethod
    def _ensure_message_emojis(cls, text: str) -> str:
        lines = text.splitlines()
        non_empty_indexes = [idx for idx, line in enumerate(lines) if line.strip()]
        if not non_empty_indexes:
            return text

        emoji_count = cls._count_emojis(text)
        if emoji_count == 0:
            first_idx = non_empty_indexes[0]
            lines[first_idx] = f"✨ {lines[first_idx].lstrip()}"
            emoji_count = 1

        if emoji_count < 2:
            practical_idx = next(
                (idx for idx in non_empty_indexes if lines[idx].strip().lower().startswith("практически")),
                None,
            )
            if practical_idx is not None and cls._count_emojis(lines[practical_idx]) == 0:
                lines[practical_idx] = f"🧴 {lines[practical_idx].lstrip()}"
            else:
                inserted = False
                for idx in reversed(non_empty_indexes):
                    if cls._count_emojis(lines[idx]) == 0:
                        lines[idx] = f"💬 {lines[idx].lstrip()}"
                        inserted = True
                        break
                if not inserted:
                    first_idx = non_empty_indexes[0]
                    lines[first_idx] = f"{lines[first_idx].rstrip()} 💬"

        return "\n".join(lines)

    @classmethod
    def _enforce_emoji_budget(cls, text: str, max_emojis: int = 2) -> str:
        seen = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal seen
            seen += 1
            if seen <= max_emojis:
                return match.group(0)
            return ""

        compact = cls._EMOJI_PATTERN.sub(_replace, text)
        compact = re.sub(r"[ ]{2,}", " ", compact)
        compact = re.sub(r"\n{3,}", "\n\n", compact)
        return compact.strip()

    @classmethod
    def _count_emojis(cls, text: str) -> int:
        return len(cls._EMOJI_PATTERN.findall(text))

    @staticmethod
    def _count_bold_fragments(text: str) -> int:
        return len(re.findall(r"\*[^*\n]+\*", text))

    @classmethod
    def _strip_soft_closing_tail(cls, text: str) -> str:
        lines = text.splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return ""

        last = lines[-1].strip()
        if any(last.lower() == closing.lower() for closing in cls._SOFT_CLOSINGS):
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()

        return "\n".join(lines).strip()

    @classmethod
    def _has_explicit_purchase_intent(cls, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in cls._EXPLICIT_PURCHASE_MARKERS)

    @classmethod
    def _is_cta_line(cls, line: str) -> bool:
        lowered = line.lower()
        return lowered.startswith(cls._CTA_START_MARKERS)

    @classmethod
    def _is_reaction_line(cls, line: str) -> bool:
        lowered = line.lower().strip(" .!?,")
        return any(lowered.startswith(marker) for marker in cls._REACTION_STARTERS)

    @staticmethod
    def _last_assistant_opening(session: UserSession) -> str:
        last_assistant = next(
            (turn.content for turn in reversed(session.history) if turn.role == "assistant" and turn.content.strip()),
            "",
        )
        if not last_assistant:
            return ""
        first_line = next((line.strip() for line in last_assistant.splitlines() if line.strip()), "")
        return first_line.lower()

    @classmethod
    def _is_doubt_or_objection(cls, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(marker in lowered for marker in cls._DOUBT_MARKERS)

    @staticmethod
    def _technical_pause_fallback() -> str:
        return "Вижу небольшую техническую паузу.\nПопробуйте ещё раз через несколько секунд."

    @staticmethod
    def _fallback_for_mode(mode: ChatMode) -> str:
        if mode == ChatMode.CONSULTATION:
            return "Понимаю Ваш запрос. Давайте мягко разберём уход по шагам и добавим безопасный следующий шаг."
        if mode == ChatMode.SKIN_TYPE:
            return "Понимаю Ваш запрос. Дам ориентир по типу кожи и практическую рекомендацию по уходу."
        if mode == ChatMode.PROBLEM_SOLVING:
            return "Понимаю, это может беспокоить. Давайте разберём ситуацию и выберем безопасный план действий."
        if mode == ChatMode.INGREDIENT_CHECK:
            return "Очень хороший вопрос. Давайте разберём состав по безопасности и практическому применению."
        return "Понимаю Ваш вопрос. Давайте разберём его и определим конкретный следующий шаг по уходу."
