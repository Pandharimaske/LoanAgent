"""
Summarization utilities for conversation compression.
Uses local LLM to create summaries when token threshold is exceeded.
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.ollama_client import OllamaClient
from utils.tokenizer import TokenCounter


class SensitiveDataMasker:
    """Mask PII before sending to LLM."""

    @staticmethod
    def mask_pan(text: str) -> str:
        """Mask PAN number (Indian tax ID: 5 letters + 4 digits + letter)."""
        return re.sub(r"\b[A-Z]{5}\d{4}[A-Z]\b", "[PAN_REDACTED]", text)

    @staticmethod
    def mask_phone(text: str) -> str:
        """Mask phone numbers."""
        return re.sub(r"\b\d{10}\b", "[PHONE_REDACTED]", text)

    @staticmethod
    def mask_amounts(text: str) -> str:
        """Mask amount values (₹ or rupees)."""
        # ₹45,000 or ₹45000 or 45000 rupees
        text = re.sub(r"₹[\d,]+", "[AMOUNT_REDACTED]", text)
        text = re.sub(
            r"\b\d+(?:\s*(?:rupees|lakhs|lakh|crore|cr))\b",
            "[AMOUNT_REDACTED]",
            text,
            flags=re.IGNORECASE,
        )
        return text

    @staticmethod
    def mask_addresses(text: str) -> str:
        """Mask street addresses (simple heuristic)."""
        # If line contains common address keywords, mask it
        lines = text.split("\n")
        masked_lines = []
        for line in lines:
            if any(
                keyword in line.lower()
                for keyword in [
                    "street",
                    "road",
                    "avenue",
                    "colony",
                    "sector",
                    "plot",
                    "apartment",
                ]
            ):
                masked_lines.append("[ADDRESS_REDACTED]")
            else:
                masked_lines.append(line)
        return "\n".join(masked_lines)

    @staticmethod
    def mask_all(text: str) -> str:
        """Apply all masking rules."""
        text = SensitiveDataMasker.mask_pan(text)
        text = SensitiveDataMasker.mask_phone(text)
        text = SensitiveDataMasker.mask_amounts(text)
        text = SensitiveDataMasker.mask_addresses(text)
        return text


class ConversationSummarizer:
    """Summarize conversations using local LLM."""

    SUMMARIZATION_PROMPT = """You are a bank loan assistant. Summarize the following conversation concisely.

IMPORTANT: Focus on:
- Customer name (if mentioned)
- Income (preserved exactly)
- Co-applicant information
- Loan amount requested
- Employment type
- Any documents or liabilities mentioned
- Unresolved issues or pending confirmations

Keep summary to 3-5 sentences max. Be precise and preserve all financial details.

Conversation:
{conversation}

Summary:"""

    def __init__(self, ollama_client: OllamaClient = None):
        """
        Initialize summarizer.
        
        Args:
            ollama_client: Optional OllamaClient instance. If None, creates a new one.
        """
        self.client = ollama_client

    async def summarize(
        self,
        messages: List[Dict[str, str]],
        mask_sensitive: bool = True,
        temperature: float = 0.3,
    ) -> str:
        """
        Summarize a list of messages.
        
        Args:
            messages: List of {"role": "...", "content": "..."} dicts
            mask_sensitive: Whether to mask PII before sending to LLM
            temperature: LLM temperature (lower = more consistent)
            
        Returns:
            Summarized text
            
        Raises:
            RuntimeError: If summarization fails
        """
        if not messages:
            return "[Empty conversation]"

        # Convert messages to readable format
        conversation_text = self._format_messages(messages)

        # Mask sensitive data if requested
        if mask_sensitive:
            conversation_text = SensitiveDataMasker.mask_all(
                conversation_text
            )

        # Get or create client
        client = self.client
        close_after = False
        if client is None:
            from config import OLLAMA_BASE_URL, OLLAMA_MODEL
            client = OllamaClient()
            close_after = True

        try:
            # Generate summary
            summary = await client.generate(
                prompt=self.SUMMARIZATION_PROMPT.format(
                    conversation=conversation_text
                ),
                temperature=temperature,
            )

            return summary.strip()

        finally:
            if close_after:
                await client.close()

    @staticmethod
    def _format_messages(messages: List[Dict[str, str]]) -> str:
        """Format message list as readable string."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)


class CompressionManager:
    """Orchestrate conversation compression workflow."""

    def __init__(self, ollama_client: OllamaClient = None):
        """
        Initialize compression manager.
        
        Args:
            ollama_client: Optional OllamaClient instance
        """
        self.summarizer = ConversationSummarizer(ollama_client)

    async def compress_if_needed(
        self, messages: List[Dict[str, str]]
    ) -> Dict[str, any]:
        """
        Check if compression is needed and compress if so.
        
        Args:
            messages: Conversation history
            
        Returns:
            Dict with compression results or None if no compression needed
        """
        current_tokens = TokenCounter.count_messages(messages)

        if not TokenCounter.should_summarize(current_tokens):
            return {
                "compressed": False,
                "reason": "Token count below threshold",
                "total_tokens": current_tokens,
                "threshold": TokenCounter.get_threshold_tokens(),
            }

        print(f"\n🔄 Compression triggered!")
        print(
            f"   Current tokens: {current_tokens} / "
            f"{TokenCounter.get_threshold_tokens()}"
        )

        # Split messages: oldest 50% to summarize, newest 50% to keep
        count = max(1, len(messages) // 2)
        messages_to_summarize = messages[:count]
        messages_to_keep = messages[count:]

        print(f"   Summarizing {count} old turns...")

        # Generate summary
        summary = await self.summarizer.summarize(
            messages_to_summarize,
            mask_sensitive=True,
        )

        # Replace old messages with summary
        compressed_messages = (
            [{"role": "system", "content": f"[SESSION SUMMARY]\n{summary}"}]
            + messages_to_keep
        )

        new_tokens = TokenCounter.count_messages(compressed_messages)

        return {
            "compressed": True,
            "old_turns": count,
            "summary": summary,
            "old_tokens": current_tokens,
            "new_tokens": new_tokens,
            "compression_ratio": new_tokens / current_tokens
            if current_tokens > 0
            else 1.0,
            "messages": compressed_messages,
        }


# ============================================================================
# TEST UTILITIES
# ============================================================================


def test_sensitive_data_masker():
    """Test PII masking."""
    print("\n" + "=" * 70)
    print("🔐 Testing Sensitive Data Masking")
    print("=" * 70)

    test_text = """
    Customer: My name is Rajesh Kumar
    PAN: ABCDE1234F
    Phone: 9876543210
    Income: ₹45,000 per month
    Address: 123 Main Street, Sector 5, Bangalore
    Loan amount: 25 lakhs
    """

    print(f"\nOriginal:\n{test_text}")

    masked = SensitiveDataMasker.mask_all(test_text)
    print(f"\nMasked:\n{masked}")


async def test_summarization():
    """Test live summarization with Ollama."""
    print("\n" + "=" * 70)
    print("📝 Testing Conversation Summarization")
    print("=" * 70)

    messages = [
        {
            "role": "user",
            "content": "Hello, I need a home loan for ₹25 lakhs.",
        },
        {
            "role": "assistant",
            "content": "Sure! Let me help you. What's your annual income?",
        },
        {
            "role": "user",
            "content": "It's ₹45,000 per month, so about ₹5.4 lakhs per year.",
        },
        {
            "role": "assistant",
            "content": "Good. Do you have a co-applicant?",
        },
        {
            "role": "user",
            "content": "Yes, my wife Sunita will be co-applicant.",
        },
        {
            "role": "assistant",
            "content": "Perfect. Can you provide her income details?",
        },
    ]

    print("\nConversation:")
    for msg in messages:
        print(f"  {msg['role'].upper()}: {msg['content']}")

    try:
        summarizer = ConversationSummarizer()
        summary = await summarizer.summarize(messages)
        print(f"\n✅ Summary:\n{summary}")
    except Exception as e:
        print(f"❌ Summarization failed: {e}")


async def test_compression_manager():
    """Test full compression workflow."""
    print("\n" + "=" * 70)
    print("🗜️ Testing Compression Manager")
    print("=" * 70)

    # Create a large conversation to trigger compression
    messages = [
        {"role": "user", "content": f"Message {i}: Customer details about their financial situation."}
        for i in range(20)
    ]
    messages += [
        {
            "role": "assistant",
            "content": f"Response {i}: Understanding your situation.",
        }
        for i in range(20)
    ]

    print(f"\nCreated {len(messages)} messages")

    current_tokens = TokenCounter.count_messages(messages)
    threshold = TokenCounter.get_threshold_tokens()

    print(f"Current tokens: {current_tokens}")
    print(f"Threshold: {threshold}")
    print(f"Will trigger compression: {current_tokens > threshold}")

    if current_tokens > threshold:
        manager = CompressionManager()
        result = await manager.compress_if_needed(messages)

        print(f"\n✅ Compression Result:")
        print(
            f"   Old tokens: {result.get('old_tokens')} "
            f"→ New tokens: {result.get('new_tokens')}"
        )
        print(
            f"   Compression ratio: {result.get('compression_ratio'):.2f}x"
        )
        print(f"   Summary:\n   {result.get('summary')}")


if __name__ == "__main__":
    import asyncio

    test_sensitive_data_masker()
    asyncio.run(test_summarization())
    asyncio.run(test_compression_manager())
