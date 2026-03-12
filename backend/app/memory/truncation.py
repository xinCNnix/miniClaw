"""
Truncation Module - Token Management Strategies

This module handles text truncation for long prompts and messages.
"""

from typing import Optional, List
import re


class TextTruncator:
    """
    Text truncation utility for managing long prompts and messages.

    Provides multiple strategies for truncating text while preserving
    important information.
    """

    def __init__(self, max_length: int = 20000, marker: str = "...[truncated]"):
        """
        Initialize the truncator.

        Args:
            max_length: Maximum length before truncation
            marker: Marker to add when truncating
        """
        self.max_length = max_length
        self.marker = marker

    def truncate(
        self,
        text: str,
        strategy: str = "end",
    ) -> str:
        """
        Truncate text using specified strategy.

        Args:
            text: Text to truncate
            strategy: Truncation strategy ('end', 'middle', 'smart')

        Returns:
            Truncated text

        Strategies:
        - end: Keep the beginning, truncate the end
        - middle: Truncate from the middle
        - smart: Try to truncate at sentence boundaries

        Examples:
            >>> truncator = TextTruncator(max_length=100)
            >>> short = truncator.truncate(long_text)
            >>> print(short)
        """
        if len(text) <= self.max_length:
            return text

        if strategy == "end":
            return self._truncate_end(text)
        elif strategy == "middle":
            return self._truncate_middle(text)
        elif strategy == "smart":
            return self._truncate_smart(text)
        else:
            return self._truncate_end(text)

    def _truncate_end(self, text: str) -> str:
        """Truncate from the end."""
        available = self.max_length - len(self.marker)
        return text[:available] + self.marker

    def _truncate_middle(self, text: str) -> str:
        """Truncate from the middle."""
        available = (self.max_length - len(self.marker)) // 2
        return text[:available] + self.marker + text[-available:]

    def _truncate_smart(self, text: str) -> str:
        """
        Truncate at sentence boundaries.

        Tries to find a good breaking point (end of sentence)
        rather than cutting in the middle of text.
        """
        if len(text) <= self.max_length:
            return text

        # Find last sentence before max_length
        truncate_point = self.max_length - len(self.marker)

        # Look for sentence endings
        sentence_endings = r"([.!?。！？]\s+)"

        # Search backwards from truncate_point
        for i in range(truncate_point, 0, -10):
            snippet = text[max(0, i-50):i]
            matches = list(re.finditer(sentence_endings, snippet))

            if matches:
                # Found a sentence ending
                match = matches[-1]
                end_pos = i - (len(snippet) - match.end() - 1)

                if end_pos > 0:
                    return text[:end_pos] + self.marker

        # No good sentence ending found, fall back to end truncation
        return self._truncate_end(text)

    def truncate_messages(
        self,
        messages: List[dict],
        max_total_length: int,
        strategy: str = "recent",
    ) -> List[dict]:
        """
        Truncate a list of messages to fit within max length.

        Args:
            messages: List of message dicts
            max_total_length: Maximum total length
            strategy: 'recent' (keep most recent) or 'balanced' (mix old and new)

        Returns:
            Truncated message list

        Examples:
            >>> truncator = TextTruncator()
            >>> messages = [...]
            >>> short = truncator.truncate_messages(messages, 1000)
            >>> print(f"Kept {len(short)} out of {len(messages)} messages")
        """
        if strategy == "recent":
            return self._truncate_messages_recent(messages, max_total_length)
        elif strategy == "balanced":
            return self._truncate_messages_balanced(messages, max_total_length)
        else:
            return self._truncate_messages_recent(messages, max_total_length)

    def _truncate_messages_recent(
        self,
        messages: List[dict],
        max_total_length: int,
    ) -> List[dict]:
        """
        Keep most recent messages.

        Args:
            messages: List of messages
            max_total_length: Maximum total length

        Returns:
            Truncated message list (most recent first)
        """
        result = []
        current_length = 0

        # Iterate in reverse (most recent first)
        for message in reversed(messages):
            # Calculate message length
            msg_length = len(message.get("content", ""))

            if current_length + msg_length > max_total_length:
                break

            # Prepend (to maintain order)
            result.insert(0, message)
            current_length += msg_length

        return result

    def _truncate_messages_balanced(
        self,
        messages: List[dict],
        max_total_length: int,
    ) -> List[dict]:
        """
        Keep a balanced mix of old and new messages.

        Args:
            messages: List of messages
            max_total_length: Maximum total length

        Returns:
            Truncated message list

        Strategy:
        - Always keep the first message (context)
        - Always keep the last few messages (recent context)
        - Fill middle with alternating old/new messages
        """
        if not messages:
            return []

        # Keep first message
        result = [messages[0]]
        current_length = len(messages[0].get("content", ""))

        # Keep last 3 messages if possible
        recent_count = min(3, len(messages))
        recent_messages = messages[-recent_count:]

        for msg in reversed(recent_messages[:-1] if recent_count > 1 else []):
            msg_length = len(msg.get("content", ""))

            if current_length + msg_length <= max_total_length:
                result.append(msg)
                current_length += msg_length

        # Fill in middle messages
        middle_messages = messages[1:-recent_count] if len(messages) > recent_count + 1 else []

        for i, msg in enumerate(middle_messages):
            msg_length = len(msg.get("content", ""))

            if current_length + msg_length > max_total_length:
                break

            if i % 2 == 0:  # Take every other message
                result.append(msg)
                current_length += msg_length

        # Sort to maintain original order
        result.sort(key=lambda m: messages.index(m) if m in messages else float('inf'))

        return result

    def summarize_messages(self, messages: List[dict]) -> str:
        """
        Create a summary of messages for long-term memory.

        Args:
            messages: List of message dicts

        Returns:
            Summary string

        Examples:
            >>> truncator = TextTruncator()
            >>> messages = session['messages']
            >>> summary = truncator.summarize_messages(messages)
            >>> print(summary)
        """
        if not messages:
            return "No messages to summarize."

        # Count message types
        user_count = sum(1 for m in messages if m.get("role") == "user")
        assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
        tool_count = sum(1 for m in messages if m.get("role") == "tool")

        # Extract key topics from user messages
        user_messages = [m.get("content", "") for m in messages if m.get("role") == "user"]

        # Simple keyword extraction
        keywords = set()
        for msg in user_messages:
            words = re.findall(r"\b\w{4,}\b", msg.lower())
            keywords.update(words[:5])  # Take first 5 words per message

        # Build summary
        summary_parts = [
            f"Conversation Summary:",
            f"- Total messages: {len(messages)}",
            f"- User messages: {user_count}",
            f"- Assistant responses: {assistant_count}",
            f"- Tool calls: {tool_count}",
            f"",
            f"Topics discussed: {', '.join(list(keywords)[:10])}",
        ]

        return "\n".join(summary_parts)


def truncate_prompt(
    prompt: str,
    max_length: int = 20000,
    marker: str = "...[truncated]",
) -> str:
    """
    Truncate a prompt to max length.

    Args:
        prompt: Prompt to truncate
        max_length: Maximum length
        marker: Truncation marker

    Returns:
        Truncated prompt

    Examples:
        >>> from app.memory.truncation import truncate_prompt
        >>> short = truncate_prompt(long_prompt)
    """
    truncator = TextTruncator(max_length=max_length, marker=marker)
    return truncator.truncate(prompt, strategy="smart")


def truncate_message_list(
    messages: List[dict],
    max_length: int = 10000,
) -> List[dict]:
    """
    Truncate a list of messages.

    Args:
        messages: List of messages
        max_length: Maximum total length

    Returns:
        Truncated message list

    Examples:
        >>> from app.memory.truncation import truncate_message_list
        >>> short = truncate_message_list(messages)
        >>> print(f"Kept {len(short)} messages")
    """
    truncator = TextTruncator(max_length=max_length)
    return truncator.truncate_messages(messages, max_length, strategy="recent")
