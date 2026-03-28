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
    # Numbers in Hindi (Roman)
    "ek", "do", "teen", "char", "paanch", "chhe", "saat", "aath", "nau", "das",
    "bees", "tees", "pachas", "sau", "hazaar", "lakh", "crore",
    # Loan-domain specific
    "loan", "rin", "byaj", "faida", "mahina", "saal",
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
      2. If ≥2 Hinglish keywords found in the lowercased text → "hinglish"
      3. Otherwise → "en"
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

    # Step 2: Hinglish keyword match
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    matches = words & _HINGLISH_KEYWORDS
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

    try:
        response = await llm.ainvoke(prompt)
        translated = (response.content if hasattr(response, "content") else str(response)).strip()

        # Sanity check — if translation is empty or absurdly long, fall back
        if not translated or len(translated) > len(text) * 5:
            logger.warning("translate_to_english: suspicious result, using original")
            return text

        logger.info(f"🌐 Translated ({lang}→en): '{text[:40]}' → '{translated[:40]}'")
        return translated

    except Exception as e:
        logger.warning(f"⚠️  translate_to_english failed ({e}), using original input")
        return text


# ============================================================================
# TRANSLATE RESPONSE → USER'S LANGUAGE
# ============================================================================

_TRANSLATE_TO_LANG_PROMPT = """\
You are a translator for a loan-advisory chatbot.
Translate the following English response into {lang_label}.

Rules:
- Keep all numbers, currency amounts (₹), percentages, and proper nouns unchanged.
- Keep technical loan terms (CIBIL, EMI, FOIR, LTV, PMAY) in English — do not translate them.
- Keep the same tone: professional but friendly.
{extra_rules}
Output ONLY the translated text — no explanation, no preamble.

English text:
{text}

{lang_label} translation:"""

_EXTRA_RULES = {
    "hi": (
        "- Write in standard Hindi using Devanagari script.\n"
        "- Use formal/polite forms (आप)."
    ),
    "hinglish": (
        "- Write in casual Hinglish — Hindi words in Roman script mixed with English.\n"
        "- Use the natural way urban Indians speak, e.g. 'Aapka CIBIL score 750 hai, "
        "jo home loan ke liye suitable hai.'\n"
        "- Do NOT use Devanagari script."
    ),
}


async def translate_to_user_language(text: str, lang: Language, llm) -> str:
    """
    Translate the English agent response back to the user's language.
    Returns the original text unchanged if lang=="en".

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
    prompt = _TRANSLATE_TO_LANG_PROMPT.format(
        lang_label=label, text=text.strip(), extra_rules=extra
    )

    try:
        response = await llm.ainvoke(prompt)
        translated = (response.content if hasattr(response, "content") else str(response)).strip()

        if not translated or len(translated) > len(text) * 6:
            logger.warning("translate_to_user_language: suspicious result, using English")
            return text

        logger.info(f"🌐 Translated (en→{lang}): '{text[:40]}' → '{translated[:40]}'")
        return translated

    except Exception as e:
        logger.warning(f"⚠️  translate_to_user_language failed ({e}), using English response")
        return text
