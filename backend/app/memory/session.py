"""
Session Module - Conversation Session Management

This module handles storage and retrieval of conversation sessions.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config import get_settings


class SessionManager:
    """
    Manager for conversation sessions.

    Sessions are stored as JSON files in the sessions directory.
    """

    def __init__(self):
        """Initialize the session manager."""
        settings = get_settings()
        self.sessions_dir = Path(settings.sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Create a new session.

        Args:
            session_id: Optional custom session ID
            metadata: Optional metadata for the session

        Returns:
            Session dict

        Examples:
            >>> manager = SessionManager()
            >>> session = manager.create_session()
            >>> print(session['session_id'])
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        session = {
            "session_id": session_id,
            "messages": [],
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        # Save to file
        self.save_session(session)

        return session

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session dict or None if not found

        Examples:
            >>> manager = SessionManager()
            >>> session = manager.load_session("some-id")
            >>> if session:
            ...     print(f"Loaded session with {len(session['messages'])} messages")
        """
        session_file = self.sessions_dir / f"{session_id}.json"

        if not session_file.exists():
            return None

        try:
            content = session_file.read_text(encoding="utf-8")
            session = json.loads(content)
            return session
        except Exception:
            return None

    def save_session(self, session: Dict[str, Any]) -> None:
        """
        Save a session to disk.

        Args:
            session: Session dict

        Raises:
            ValueError: If session is invalid

        Examples:
            >>> manager = SessionManager()
            >>> session = manager.load_session("some-id")
            >>> session['messages'].append({"role": "user", "content": "Hello"})
            >>> manager.save_session(session)
        """
        if "session_id" not in session:
            raise ValueError("Session must have session_id")

        # Update timestamp
        session["updated_at"] = datetime.now().isoformat()

        # Save to file
        session_file = self.sessions_dir / f"{session['session_id']}.json"

        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2, ensure_ascii=False)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict]] = None,
        images: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Add a message to a session.

        Args:
            session_id: Session ID
            role: Message role (user/assistant/tool)
            content: Message content
            tool_calls: Optional tool calls (for role=tool)
            images: Optional image attachments (for multimodal LLMs)

        Returns:
            Updated session or None if session not found

        Examples:
            >>> manager = SessionManager()
            >>> session = manager.add_message(
            ...     "some-id",
            ...     "user",
            ...     "Hello!"
            ... )
        """
        session = self.load_session(session_id)

        if session is None:
            return None

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }

        if tool_calls:
            message["tool_calls"] = tool_calls

        if images:
            message["images"] = images

        session["messages"].append(message)

        # Enforce max message limit
        settings = get_settings()
        max_messages = settings.max_message_history

        if len(session["messages"]) > max_messages:
            # Keep only the most recent messages
            session["messages"] = session["messages"][-max_messages:]

        self.save_session(session)
        return session

    def get_messages(self, session_id: str) -> List[Dict]:
        """
        Get all messages from a session.

        Args:
            session_id: Session ID

        Returns:
            List of message dicts

        Examples:
            >>> manager = SessionManager()
            >>> messages = manager.get_messages("some-id")
            >>> for msg in messages:
            ...     print(f"{msg['role']}: {msg['content'][:50]}")
        """
        session = self.load_session(session_id)

        if session is None:
            return []

        return session.get("messages", [])

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all sessions.

        Returns:
            List of session info dicts

        Examples:
            >>> manager = SessionManager()
            >>> sessions = manager.list_sessions()
            >>> for s in sessions:
            ...     print(f"{s['session_id']}: {s['metadata'].get('title', 'Untitled')}")
        """
        sessions = []

        for session_file in self.sessions_dir.glob("*.json"):
            try:
                content = session_file.read_text(encoding="utf-8")
                session = json.loads(content)

                # Return summary info only
                sessions.append({
                    "session_id": session["session_id"],
                    "created_at": session.get("created_at"),
                    "updated_at": session.get("updated_at"),
                    "message_count": len(session.get("messages", [])),
                    "metadata": session.get("metadata", {}),
                })

            except Exception:
                # Skip invalid sessions
                continue

        # Sort by updated_at (newest first)
        sessions.sort(
            key=lambda s: s.get("updated_at", ""),
            reverse=True
        )

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False if not found

        Examples:
            >>> manager = SessionManager()
            >>> success = manager.delete_session("some-id")
            >>> print(f"Deleted: {success}")
        """
        session_file = self.sessions_dir / f"{session_id}.json"

        if not session_file.exists():
            return False

        try:
            session_file.unlink()
            return True
        except Exception:
            return False

    def get_session_stats(self, session_id: str) -> Optional[Dict]:
        """
        Get statistics about a session.

        Args:
            session_id: Session ID

        Returns:
            Dict with stats or None

        Examples:
            >>> manager = SessionManager()
            >>> stats = manager.get_session_stats("some-id")
            >>> print(stats)
        """
        session = self.load_session(session_id)

        if session is None:
            return None

        messages = session.get("messages", [])

        # Count message types
        user_messages = sum(1 for m in messages if m.get("role") == "user")
        assistant_messages = sum(1 for m in messages if m.get("role") == "assistant")
        tool_messages = sum(1 for m in messages if m.get("role") == "tool")

        return {
            "total_messages": len(messages),
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "tool_messages": tool_messages,
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
        }


def get_session_manager() -> SessionManager:
    """
    Get the global session manager instance.

    Returns:
        SessionManager instance

    Examples:
        >>> from app.memory.session import get_session_manager
        >>> manager = get_session_manager()
        >>> sessions = manager.list_sessions()
    """
    return SessionManager()
