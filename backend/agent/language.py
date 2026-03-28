"""
Language detection and translation utilities for LoanAgent.

Architecture:
  User input (any language)
    → detect_language()
    → translate_to_english()          # only if not English
    → [ENTIRE PIPELINE — unchanged]
    → translate_to_user_language()    # only if not English
    → Final response in user's language

The pipeline always runs in English. Translation is a transparent wrapper.
"""

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

Language = Literal["en", "hi", "hinglish"]

# ============================================================================
# HINDI KEYWORD LIST  (Roman-script Hinglish indicators)
# ============================================================================

_HINGLISH_KEYWORDS = {
    # Pronouns & possessives
    "mera", "meri", "mere", "mujhe", "mujhko", "humara", "hamara",
    "aapka", "aapki", "aapke", "tumhara", "tumhari",
    # Question words
    "kya", "kitna", "kitni", "kaise", "kaun", "kab", "kahan", "kyun",
    # Verbs / aux
    "hai", "hain", "tha", "thi", "hoga", "hogi", "chahiye", "chahta",
    "milega", "milegi", "karunga", "karna", "batao", "boliye", "samjhao",
    # Common words
    "nahi", "nahin", "aur", "lekin", "toh", "bhi", "se", "ko", "ka",
    "ki", "ke", "par", "mein", "pe", "wala", "wali",
    # Short affirmations / confirmations common in Hinglish
    "haan", "naa", "accha", "theek", "bilkul", "zaroor", "shukriya",
    "dhanyawad", "namaste", "bolo", "dekho",
    # Numbers in Hindi (Roman)
    "ek", "do", "teen", "char", "paanch", "chhe", "saat", "aath", "nau", "das",
    "bees", "tees", "pachas", "sau", "hazaar", "lakh", "crore",
    # Loan-domain specific
    "rin", "byaj", "faida", "mahina", "saal",
}

# Single-word triggers — if the ENTIRE message (stripped) is one of these,
# treat it as Hinglish regardless of the ≥2 keyword rule.
_HINGLISH_SINGLE_WORD = {
    "haan", "naa", "accha", "theek", "bilkul", "zaroor", "shukriya",
    "dhanyawad", "namaste", "batao", "bolo", "dekho", "chaliye",
    "samjha", "samjhi", "samajh", "hmm",
}

# ============================================================================
# DETECT LANGUAGE
# ============================================================================

def detect_language(text: str) -> Language:
    """
    Detect the language of user input.

    Returns:
        "hi"       — text is primarily in Hindi (Devanagari script)
        "hinglish" — text is Hindi written in Roman script / mixed
        "en"       — text is in English (default)

    Heuristic:
      1. If ≥15% of non-space characters are Devanagari → "hi"
      2. If entire message (single word) is a known Hinglish word → "hinglish"
      3. If ≥1 Hinglish keyword found AND message is short (≤4 words) → "hinglish"
      4. If ≥2 Hinglish keywords found → "hinglish"
      5. Otherwise → "en"

    FIX: Lowered the keyword threshold for SHORT messages so that follow-up
    replies like "haan", "theek hai", "batao" are correctly kept as Hinglish
    instead of reverting to "en".
    """
    if not text or not text.strip():
        return "en"

    # Step 1: Devanagari character ratio
    chars = [c for c in text if c != " "]
    if chars:
        devanagari = sum(1 for c in chars if "\u0900" <= c <= "\u097F")
        ratio = devanagari / len(chars)
        if ratio >= 0.15:
            logger.debug(f"detect_language → hi (Devanagari ratio={ratio:.2f})")
            return "hi"

    # Step 2: Single-word Hinglish trigger
    single = text.strip().lower()
    if single in _HINGLISH_SINGLE_WORD:
        logger.debug(f"detect_language → hinglish (single-word: {single!r})")
        return "hinglish"

    # Step 3 & 4: Keyword match with context-aware threshold
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    matches = words & _HINGLISH_KEYWORDS
    word_count = len(re.findall(r"\S+", text.strip()))

    # Short messages (≤4 words) only need 1 keyword hit
    if word_count <= 4 and len(matches) >= 1:
        logger.debug(f"detect_language → hinglish (short msg, keyword: {matches})")
        return "hinglish"

    # Longer messages need ≥2 keyword hits
    if len(matches) >= 2:
        logger.debug(f"detect_language → hinglish (keywords: {matches})")
        return "hinglish"

    return "en"


# ============================================================================
# TRANSLATE INPUT → ENGLISH
# ============================================================================

_TRANSLATE_TO_EN_PROMPT = """\
You are a translator for a loan-advisory chatbot.
Translate the following message to clear, natural English.
Preserve all numbers, currency amounts, proper nouns, and financial terms exactly.
Output ONLY the translated English text — no explanation, no preamble.

Original ({lang_label}):
{text}

English translation:"""

_LANG_LABELS = {
    "hi": "Hindi",
    "hinglish": "Hinglish (Hindi in Roman script)",
}


async def translate_to_english(text: str, lang: Language, llm) -> str:
    """
    Translate user input to English using the provided LLM instance.
    Returns the original text unchanged if lang=="en".

    Args:
        text: User's message in any language
        lang: Detected language ("hi" | "hinglish" | "en")
        llm:  ChatOllama instance (or any LangChain chat model)

    Returns:
        English translation of the text.
    """
    if lang == "en" or not text.strip():
        return text

    label = _LANG_LABELS.get(lang, lang)
    prompt = _TRANSLATE_TO_EN_PROMPT.format(lang_label=label, text=text.strip())

    for attempt in range(2):
        try:
            response = await llm.ainvoke(prompt)
            translated = (response.content if hasattr(response, "content") else str(response)).strip()

            # Sanity check — if translation is empty or absurdly long, retry/fall back
            if not translated:
                logger.warning(f"translate_to_english: empty result (attempt {attempt + 1}), retrying...")
                continue
            if len(translated) > len(text) * 8:
                logger.warning(f"translate_to_english: result too long (attempt {attempt + 1}), retrying...")
                continue

            logger.info(f"🌐 Translated ({lang}→en): '{text[:40]}' → '{translated[:40]}'")
            return translated

        except Exception as e:
            logger.warning(f"⚠️  translate_to_english attempt {attempt + 1} failed: {e}")

    logger.warning("translate_to_english: all attempts failed, using original input")
    return text


# ============================================================================
# TRANSLATE RESPONSE → USER'S LANGUAGE
# ============================================================================

_TRANSLATE_TO_LANG_PROMPT = """\
You are a professional translator for a loan-advisory chatbot.
Your ONLY job is to translate the given English text into {lang_label}.
You MUST produce a translation — never return English or an empty response.

Translation rules:
- Keep all numbers, currency amounts (₹), percentages, and proper nouns unchanged.
- Keep technical loan terms (CIBIL, EMI, FOIR, LTV, PMAY, RBI) in English — do not translate them.
- Keep the same tone: professional but friendly.
{extra_rules}

CRITICAL: Output ONLY the translated {lang_label} text.
Do NOT include the original English text.
Do NOT add any explanation, label, or preamble like "Translation:" or "Here is:".

English text to translate:
{text}

{lang_label} translation (output ONLY the translated text):"""

_EXTRA_RULES = {
    "hi": (
        "- Write in SIMPLE, EVERYDAY Hindi using Devanagari script.\n"
        "- Use the Hindi that a common person speaks — short sentences, easy words.\n"
        "- NOT formal or literary Hindi. Avoid complex or bureaucratic words.\n"
        "- Use polite forms (आप, आपका) but keep it conversational and warm.\n"
        "- BAD example (too formal): 'आपकी मासिक आय में असंगति प्रतीत होती है'\n"
        "- GOOD example (simple): 'आपने पहले ₹50,000 बताया था — अब ₹70,000 बता रहे हैं। कौन सा सही है?'\n"
        "- Every sentence must be in Hindi Devanagari script, not Roman script."
    ),
    "hinglish": (
        "- Write in casual Hinglish — Hindi words in Roman script mixed with English.\n"
        "- Use the natural way urban Indians speak, e.g.:\n"
        "  'Aapka CIBIL score 750 hai, jo home loan ke liye suitable hai.'\n"
        "  'Main aapki details save kar leta hoon.'\n"
        "- Do NOT use Devanagari script at all — only Roman (Latin) letters.\n"
        "- Mix Hindi and English naturally; don't force either language exclusively."
    ),
}

# Maximum ratio of output length to input length before we consider the
# translation suspicious. Hindi (Devanagari) text is naturally longer than
# English (more bytes per character), so we use a generous multiplier.
_MAX_LENGTH_RATIO = {
    "hi": 12,        # Devanagari characters are multi-byte → generous upper bound
    "hinglish": 8,   # Roman-script Hinglish stays closer to English length
}


def _looks_like_english(text: str) -> bool:
    """
    Heuristic: returns True if the text appears to still be in English.
    Used to detect when the LLM returned the original English instead of translating.
    """
    if not text:
        return True
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return True
    # If <5% of characters are non-ASCII, it's almost certainly English/Roman-only
    non_ascii = sum(1 for c in chars if ord(c) > 127)
    non_ascii_ratio = non_ascii / len(chars)
    return non_ascii_ratio < 0.05


async def translate_to_user_language(text: str, lang: Language, llm) -> str:
    """
    Translate the English agent response back to the user's language.
    Returns the original text unchanged if lang=="en".

    FIX: Added retry logic, better length validation, and detection of
    cases where the LLM returned English instead of the target language.

    Args:
        text: English agent response
        lang: Target language ("hi" | "hinglish" | "en")
        llm:  ChatOllama instance

    Returns:
        Translated response in the target language.
    """
    if lang == "en" or not text.strip():
        return text

    label = _LANG_LABELS.get(lang, lang)
    extra = _EXTRA_RULES.get(lang, "")
    max_ratio = _MAX_LENGTH_RATIO.get(lang, 8)

    prompt = _TRANSLATE_TO_LANG_PROMPT.format(
        lang_label=label,
        text=text.strip(),
        extra_rules=extra,
    )

    last_translated = None

    for attempt in range(3):   # up to 3 attempts
        try:
            response = await llm.ainvoke(prompt)
            translated = (response.content if hasattr(response, "content") else str(response)).strip()

            # ── Guard 1: empty result ──────────────────────────────────────
            if not translated:
                logger.warning(f"translate_to_user_language ({lang}): empty result on attempt {attempt + 1}, retrying...")
                continue

            # ── Guard 2: absurdly long result ──────────────────────────────
            if len(translated) > len(text) * max_ratio:
                logger.warning(
                    f"translate_to_user_language ({lang}): result too long "
                    f"({len(translated)} vs {len(text) * max_ratio} limit) on attempt {attempt + 1}, retrying..."
                )
                last_translated = translated
                continue

            # ── Guard 3: LLM returned English instead of target language ───
            if lang == "hi" and _looks_like_english(translated):
                logger.warning(
                    f"translate_to_user_language (hi): output looks like English on attempt {attempt + 1}, retrying..."
                )
                last_translated = translated
                continue

            logger.info(f"🌐 Translated (en→{lang}): '{text[:40]}' → '{translated[:40]}'")
            return translated

        except Exception as e:
            logger.warning(f"⚠️  translate_to_user_language ({lang}) attempt {attempt + 1} failed: {e}")

    # ── All attempts failed ────────────────────────────────────────────────
    # For Hindi: if the LLM gave us something Devanagari-looking on a previous
    # attempt but it was rejected for length, use it as a last resort — it's
    # still better than returning English.
    if last_translated and lang == "hi" and not _looks_like_english(last_translated):
        logger.warning("translate_to_user_language (hi): using best-effort result despite length warning")
        return last_translated

    logger.warning(f"translate_to_user_language ({lang}): all attempts failed — returning English response")
    return text
