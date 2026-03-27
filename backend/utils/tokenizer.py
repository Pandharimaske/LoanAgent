"""
Token counting and context management utilities.
Estimates tokens using conservative heuristics and provides compression triggers.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    SESSION_CONTEXT_WINDOW,
    TOKEN_THRESHOLD_PERCENT,
    TOKEN_TARGET_PERCENT,
)


class TokenCounter:
    """Estimate token counts for Qwen2.5-3B model."""

    # Qwen2.5-3B uses roughly 3.5 chars per token (conservative estimate)
    # Actual: ~3.4 chars/token, but we overestimate to be safe
    CHARS_PER_TOKEN = 3.5

    @staticmethod
    def count_text(text: str) -> int:
        """
        Estimate token count for a text string.
        Uses conservative character-based estimation.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        if not text:
            return 0
        return max(1, int(len(text) / TokenCounter.CHARS_PER_TOKEN))

    @staticmethod
    def count_messages(messages: List[Dict[str, str]]) -> int:
        """
        Count tokens in a conversation history.
        Adds overhead for message framing (~10 tokens per message).
        
        Args:
            messages: List of {"role": "user"/"assistant", "content": "..."}
            
        Returns:
            Estimated total token count
        """
        if not messages:
            return 0

        total = 0
        message_overhead = 10  # tokens for role, newlines, etc.

        for msg in messages:
            content = msg.get("content", "")
            total += TokenCounter.count_text(content) + message_overhead

        return total

    @staticmethod
    def get_threshold_tokens() -> int:
        """
        Get the token count at which summarization is triggered.
        This is TOKEN_THRESHOLD_PERCENT of SESSION_CONTEXT_WINDOW.
        
        Returns:
            Token count threshold (80% of context window)
        """
        return int(SESSION_CONTEXT_WINDOW * TOKEN_THRESHOLD_PERCENT)

    @staticmethod
    def get_target_tokens() -> int:
        """
        Get the target token count after summarization.
        This is TOKEN_TARGET_PERCENT of SESSION_CONTEXT_WINDOW.
        
        Returns:
            Target token count (50% of context window)
        """
        return int(SESSION_CONTEXT_WINDOW * TOKEN_TARGET_PERCENT)

    @staticmethod
    def should_summarize(current_tokens: int) -> bool:
        """
        Check if token count exceeds threshold and summarization is needed.
        
        Args:
            current_tokens: Current token count
            
        Returns:
            True if current_tokens > 80% of context window
        """
        threshold = TokenCounter.get_threshold_tokens()
        return current_tokens > threshold

    @staticmethod
    def get_compression_ratio(
        current_tokens: int,
    ) -> float:
        """
        Calculate how much compression is needed.
        
        Args:
            current_tokens: Current token count
            
        Returns:
            Compression ratio (0.0-1.0) where 1.0 = keep all tokens
        """
        target = TokenCounter.get_target_tokens()
        if current_tokens == 0:
            return 1.0
        return min(1.0, target / current_tokens)


class ContextWindow:
    """Manage and track context window usage."""

    def __init__(self, messages: List[Dict[str, str]] = None):
        """
        Initialize context window tracker.
        
        Args:
            messages: Initial message history to track
        """
        self.messages = messages or []
        self.message_tokens = {}  # Map message index to token count
        self._calculate_tokens()

    def _calculate_tokens(self):
        """Recalculate token counts for all messages."""
        self.message_tokens = {}
        for i, msg in enumerate(self.messages):
            self.message_tokens[i] = TokenCounter.count_text(
                msg.get("content", "")
            ) + 10  # +10 for message overhead

    def add_message(self, role: str, content: str) -> Dict[str, Any]:
        """
        Add a message and track tokens.
        
        Args:
            role: "user" or "assistant"
            content: Message content
            
        Returns:
            Dict with message info and current token usage
        """
        message = {"role": role, "content": content}
        self.messages.append(message)

        tokens_added = TokenCounter.count_text(content) + 10
        self.message_tokens[len(self.messages) - 1] = tokens_added

        return {
            "message": message,
            "tokens_added": tokens_added,
            "total_tokens": self.get_total_tokens(),
            "threshold": TokenCounter.get_threshold_tokens(),
            "should_summarize": self.should_summarize(),
        }

    def get_total_tokens(self) -> int:
        """Get total token count of all messages."""
        return sum(self.message_tokens.values())

    def should_summarize(self) -> bool:
        """Check if summarization is needed."""
        return TokenCounter.should_summarize(self.get_total_tokens())

    def get_oldest_turn_count(self) -> int:
        """
        Calculate how many of the oldest turns to include in summarization.
        Estimate: oldest 50% of messages.
        
        Returns:
            Number of messages (from start) to summarize
        """
        return max(1, len(self.messages) // 2)

    def get_turns_to_summarize(self) -> List[Dict[str, str]]:
        """
        Get the oldest turns (oldest 50%) to be summarized.
        
        Returns:
            List of message dicts to summarize
        """
        count = self.get_oldest_turn_count()
        return self.messages[:count]

    def get_recent_turns(self) -> List[Dict[str, str]]:
        """
        Get the recent turns (newest 50%) that will be retained verbatim.
        
        Returns:
            List of recent message dicts
        """
        count = self.get_oldest_turn_count()
        return self.messages[count:]

    def compress_with_summary(self, summary: str) -> Dict[str, Any]:
        """
        Replace oldest turns with a summary message.
        
        Args:
            summary: SLM-generated summary of old turns
            
        Returns:
            Updated message list and token info
        """
        count = self.get_oldest_turn_count()

        # Create a summary message
        summary_msg = {
            "role": "system",
            "content": f"[SESSION SUMMARY]\n{summary}",
        }

        # Replace old turns with summary
        self.messages = [summary_msg] + self.messages[count:]
        self._calculate_tokens()

        return {
            "old_turns_summarized": count,
            "new_total_tokens": self.get_total_tokens(),
            "compression_ratio": (
                self.get_total_tokens() / sum(self.message_tokens.values())
            ),
            "messages": self.messages,
        }

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive context window status."""
        total_tokens = self.get_total_tokens()
        threshold = TokenCounter.get_threshold_tokens()
        target = TokenCounter.get_target_tokens()

        return {
            "total_messages": len(self.messages),
            "total_tokens": total_tokens,
            "context_window": SESSION_CONTEXT_WINDOW,
            "threshold_tokens": threshold,
            "target_tokens": target,
            "threshold_percent": TOKEN_THRESHOLD_PERCENT * 100,
            "target_percent": TOKEN_TARGET_PERCENT * 100,
            "tokens_used_percent": (total_tokens / SESSION_CONTEXT_WINDOW)
            * 100,
            "should_summarize": total_tokens > threshold,
            "tokens_until_threshold": max(0, threshold - total_tokens),
        }


# ============================================================================
# TEST UTILITIES
# ============================================================================


def test_token_counter():
    """Test token counting and thresholds."""
    print("\n" + "=" * 70)
    print("🔢 Testing Token Counter")
    print("=" * 70)

    test_text = "My name is Rajesh, I earn ₹45,000 per year."
    tokens = TokenCounter.count_text(test_text)
    print(f"\nText: {test_text}")
    print(f"Estimated tokens: {tokens}")

    threshold = TokenCounter.get_threshold_tokens()
    target = TokenCounter.get_target_tokens()
    print(f"\nContext window: {SESSION_CONTEXT_WINDOW} tokens")
    print(f"Summarization threshold: {threshold} tokens ({TOKEN_THRESHOLD_PERCENT*100}%)")
    print(f"Target after compression: {target} tokens ({TOKEN_TARGET_PERCENT*100}%)")

    # Test message counting
    messages = [
        {
            "role": "user",
            "content": "Hello, I need a home loan for ₹25 lakhs.",
        },
        {
            "role": "assistant",
            "content": "Sure! Let me help you with that. Can you tell me about your income?",
        },
        {
            "role": "user",
            "content": "My income is ₹60,000 per month.",
        },
    ]

    msg_tokens = TokenCounter.count_messages(messages)
    print(f"\nConversation (3 messages): {msg_tokens} tokens")


def test_context_window():
    """Test context window management."""
    print("\n" + "=" * 70)
    print("📊 Testing Context Window Management")
    print("=" * 70)

    context = ContextWindow()

    # Simulate conversation
    messages = [
        ("user", "Session 1: Hello, I need a home loan."),
        ("assistant", "Sure, I'd be happy to help with your home loan application."),
        ("user", "My income is ₹45,000 per month."),
        ("assistant", "Thank you. Do you have any existing loans?"),
        ("user", "Yes, I have a car loan of ₹15,000 per month."),
    ]

    print("\nSimulating conversation:")
    for role, content in messages:
        info = context.add_message(role, content)
        print(
            f"  [{role.upper()}] {content[:50]}..."
            if len(content) > 50
            else f"  [{role.upper()}] {content}"
        )
        print(
            f"    → Tokens: +{info['tokens_added']} | "
            f"Total: {info['total_tokens']}/{TokenCounter.get_threshold_tokens()} "
            f"| Should summarize: {info['should_summarize']}"
        )

    print(f"\n📈 Final Status:")
    status = context.get_status()
    for key, value in status.items():
        if isinstance(value, float):
            print(f"   {key}: {value:.1f}")
        else:
            print(f"   {key}: {value}")

    # Test compression
    if context.should_summarize():
        print(f"\n🔄 Summarization needed!")
        result = context.compress_with_summary(
            "Customer mentioned income ₹45k/month and car EMI ₹15k/month."
        )
        print(
            f"   Old turns summarized: {result['old_turns_summarized']}"
        )
        print(f"   New total tokens: {result['new_total_tokens']}")
        print(
            f"   Compression ratio: {result['compression_ratio']:.2f}"
        )


if __name__ == "__main__":
    test_token_counter()
    test_context_window()
