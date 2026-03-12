"""
WebSocket Connection Manager

Manage WebSocket connections for real-time bidirectional communication.
"""

import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import json

logger = logging.getLogger(__name__)


class WSMessage(BaseModel):
    """WebSocket message format."""

    type: str
    data: dict
    session_id: Optional[str] = None


class ConnectionManager:
    """
    Manage WebSocket connections.

    Features:
    - Track active connections
    - Broadcast messages to all clients
    - Send messages to specific clients
    - Session-based connection grouping
    """

    def __init__(self):
        """Initialize the connection manager."""
        # Active WebSocket connections
        self.active_connections: Dict[str, WebSocket] = {}

        # Session to connection ID mapping
        self.session_connections: Dict[str, Set[str]] = {}

        # Connection to session mapping
        self.connection_sessions: Dict[str, str] = {}

    async def connect(
        self,
        websocket: WebSocket,
        connection_id: str,
        session_id: Optional[str] = None,
    ):
        """
        Accept and register a new WebSocket connection.

        Args:
            websocket: WebSocket instance
            connection_id: Unique connection identifier
            session_id: Optional session identifier for grouping
        """
        await websocket.accept()

        self.active_connections[connection_id] = websocket

        if session_id:
            if session_id not in self.session_connections:
                self.session_connections[session_id] = set()
            self.session_connections[session_id].add(connection_id)
            self.connection_sessions[connection_id] = session_id

        logger.info(
            f"WebSocket connected: {connection_id}"
            + (f" (session: {session_id})" if session_id else "")
        )

    def disconnect(self, connection_id: str):
        """
        Remove a WebSocket connection.

        Args:
            connection_id: Connection identifier
        """
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        # Remove from session mapping
        if connection_id in self.connection_sessions:
            session_id = self.connection_sessions[connection_id]
            if session_id in self.session_connections:
                self.session_connections[session_id].discard(connection_id)
                if not self.session_connections[session_id]:
                    del self.session_connections[session_id]
            del self.connection_sessions[connection_id]

        logger.info(f"WebSocket disconnected: {connection_id}")

    async def send_message(
        self,
        message: WSMessage,
        connection_id: str,
    ):
        """
        Send a message to a specific connection.

        Args:
            message: Message to send
            connection_id: Target connection identifier
        """
        if connection_id not in self.active_connections:
            logger.warning(f"Connection not found: {connection_id}")
            return

        try:
            websocket = self.active_connections[connection_id]
            await websocket.send_text(message.model_dump_json())
        except Exception as e:
            logger.error(f"Failed to send message to {connection_id}: {e}")
            self.disconnect(connection_id)

    async def broadcast(
        self,
        message: WSMessage,
        exclude_connection: Optional[str] = None,
    ):
        """
        Broadcast a message to all active connections.

        Args:
            message: Message to broadcast
            exclude_connection: Optional connection to exclude
        """
        disconnected = []

        for connection_id, websocket in self.active_connections.items():
            if exclude_connection and connection_id == exclude_connection:
                continue

            try:
                await websocket.send_text(message.model_dump_json())
            except Exception as e:
                logger.error(f"Failed to broadcast to {connection_id}: {e}")
                disconnected.append(connection_id)

        # Clean up disconnected connections
        for connection_id in disconnected:
            self.disconnect(connection_id)

    async def send_to_session(
        self,
        message: WSMessage,
        session_id: str,
        exclude_connection: Optional[str] = None,
    ):
        """
        Send a message to all connections in a session.

        Args:
            message: Message to send
            session_id: Session identifier
            exclude_connection: Optional connection to exclude
        """
        if session_id not in self.session_connections:
            logger.warning(f"Session not found: {session_id}")
            return

        disconnected = []

        for connection_id in self.session_connections[session_id]:
            if exclude_connection and connection_id == exclude_connection:
                continue

            if connection_id not in self.active_connections:
                disconnected.append(connection_id)
                continue

            try:
                websocket = self.active_connections[connection_id]
                await websocket.send_text(message.model_dump_json())
            except Exception as e:
                logger.error(f"Failed to send to {connection_id}: {e}")
                disconnected.append(connection_id)

        # Clean up disconnected connections
        for connection_id in disconnected:
            self.disconnect(connection_id)

    def get_connection_count(self) -> int:
        """
        Get the number of active connections.

        Returns:
            Number of active connections
        """
        return len(self.active_connections)

    def get_session_connection_count(self, session_id: str) -> int:
        """
        Get the number of active connections in a session.

        Args:
            session_id: Session identifier

        Returns:
            Number of active connections in the session
        """
        return len(self.session_connections.get(session_id, set()))

    def is_connected(self, connection_id: str) -> bool:
        """
        Check if a connection is active.

        Args:
            connection_id: Connection identifier

        Returns:
            True if connection is active
        """
        return connection_id in self.active_connections


# Singleton instance
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """
    Get connection manager singleton instance.

    Returns:
        Connection manager instance
    """
    global _connection_manager

    if _connection_manager is None:
        _connection_manager = ConnectionManager()

    return _connection_manager
