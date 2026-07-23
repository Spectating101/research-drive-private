import asyncio
from typing import Tuple, List, Dict, Optional
from src.services.llm_service.llm_manager import LLMManager
import os

# Helper: LLM-based intent detection
async def detect_intent_llm(llm_manager: LLMManager, user_message: str, history: List[Dict], user_profile: Optional[Dict] = None) -> Dict:
    prompt = (
        "You are an intent classifier for a content analysis assistant. "
        "Given the user's latest message and conversation history, classify the intent as one of: 'quick_context', 'deep_analysis', 'comprehensive_review', or 'clarification'. "
        "Also, classify the content type as 'news', 'articles', 'general', or 'academic'. "
        "If the user is following up for more detail, set 'escalate' to true. "
        "Return a JSON object with fields: intent, content_type, escalate, reason.\n"
        f"User message: {user_message}\n"
        f"History: {history[-5:] if history else []}\n"
        f"User profile: {user_profile or {}}\n"
    )
    # Use LLMManager to get classification
    result = await llm_manager.model_dispatcher.dispatch_document({
        'id': 'intent-detect',
        'title': 'Intent Detection',
        'content': prompt
    }, is_critical=False)
    try:
        parsed = result.get('raw_json') or result.get('raw_text') or result.get('content')
        if isinstance(parsed, str):
            import json
            parsed = json.loads(parsed)
        return parsed
    except Exception:
        return {'intent': 'quick_context', 'content_type': 'general', 'escalate': False, 'reason': 'fallback'}

async def select_research_engine(user_message: str, history: List[Dict], user_profile: Optional[Dict] = None, llm_manager: Optional[LLMManager] = None) -> Tuple[str, Dict]:
    """
    Nuanced dispatcher: selects research engine based on LLM intent detection, content type, conversation state, and user profile.
    Returns (engine_name, { 'summary': ..., 'citations': [...] })
    """
    # Use LLMManager for intent detection if available
    if llm_manager is None:
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
        llm_manager = LLMManager(redis_url)
    intent_info = await detect_intent_llm(llm_manager, user_message, history, user_profile)
    intent = intent_info.get('intent', 'quick_context')
    content_type = intent_info.get('content_type', 'general')
    escalate = intent_info.get('escalate', False)
    reason = intent_info.get('reason', '')

    # Escalation: if user is following up for more detail, escalate engine
    if escalate or (intent == 'deep_analysis' and content_type == 'academic'):
        intent = 'comprehensive_review'

    # User profile override
    if user_profile and user_profile.get('prefers_deep_analysis'):
        intent = 'comprehensive_review'
    elif user_profile and user_profile.get('prefers_quick'):
        intent = 'quick_context'

    # Engine selection
    if intent == 'comprehensive_review':
        # Comprehensive analysis engine
        from src.services.research_service.context_manager import ResearchContextManager
        # ... call comprehensive analysis, get summary and citations ...
        return ("comprehensive_review", { 'summary': "[Comprehensive analysis summary here]", 'citations': [] })
    elif intent == 'deep_analysis':
        # Deep analysis engine
        # ... call deep analysis, get summary and citations ...
        return ("deep_analysis", { 'summary': "[Deep analysis summary here]", 'citations': [] })
    elif intent == 'clarification':
        # Ask for clarification
        return ("clarification", { 'summary': "Could you clarify your question or provide more details?", 'citations': [] })
    else:
        # Quick context (surface)
        from src.services.search_service.search_engine import SearchEngine
        # ... call quick context search, get summary and citations ...
        return ("quick_context", { 'summary': "[Quick context summary here]", 'citations': [] })

# This structure is extensible: you can add more nuanced logic, hybrid/parallel engines, and richer escalation as needed. 