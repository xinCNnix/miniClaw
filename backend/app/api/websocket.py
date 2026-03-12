"""
WebSocket API

Real-time bidirectional communication endpoint.
"""

import uuid
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query

from app.core.websocket import (
    get_connection_manager,
    ConnectionManager,
    WSMessage,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None, description="Session ID for grouping"),
    manager: ConnectionManager = Depends(get_connection_manager),
):
    """
    WebSocket endpoint for real-time communication.

    This endpoint supports bidirectional real-time messaging.

    Connection URL format:
        ws://localhost:8002/api/ws?session_id={session_id}

    Message format (client -> server):
    {
        "type": "message_type",
        "data": { ... },
        "session_id": "optional_session_id"
    }

    Message format (server -> client):
    {
        "type": "message_type",
        "data": { ... },
        "session_id": "session_id"
    }

    Supported message types:
    - "ping": Keep-alive ping (server responds with "pong")
    - "chat": Chat message
    - "notification": General notification
    - "error": Error message

    Examples:
        # Client sends chat message
        {
            "type": "chat",
            "data": {"message": "Hello, AI!"},
            "session_id": "session_123"
        }

        # Server broadcasts notification
        {
            "type": "notification",
            "data": {"title": "Upload Complete", "message": "Document processed"},
            "session_id": "session_123"
        }
    """
    # Generate unique connection ID
    connection_id = str(uuid.uuid4())[:16]

    # Accept connection
    await manager.connect(websocket, connection_id, session_id)

    try:
        # Send welcome message
        welcome_msg = WSMessage(
            type="connected",
            data={
                "connection_id": connection_id,
                "session_id": session_id,
                "message": "WebSocket connection established",
            },
            session_id=session_id,
        )
        await manager.send_message(welcome_msg, connection_id)

        # Message loop
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                # Parse message
                import json
                message_data = json.loads(data)
                message = WSMessage(**message_data)

                # Handle different message types
                if message.type == "ping":
                    # Respond with pong
                    pong_msg = WSMessage(
                        type="pong",
                        data={"timestamp": message.data.get("timestamp")},
                        session_id=session_id,
                    )
                    await manager.send_message(pong_msg, connection_id)

                elif message.type == "chat":
                    # Echo chat message to session
                    chat_msg = WSMessage(
                        type="chat",
                        data=message.data,
                        session_id=session_id,
                    )
                    await manager.send_to_session(
                        chat_msg,
                        session_id or connection_id,
                        exclude_connection=connection_id,
                    )

                elif message.type == "broadcast":
                    # Broadcast to all connections
                    broadcast_msg = WSMessage(
                        type="broadcast",
                        data=message.data,
                        session_id=session_id,
                    )
                    await manager.broadcast(broadcast_msg, exclude_connection=connection_id)

                elif message.type == "notification":
                    # Handle notification (could trigger server-side action)
                    logger.info(f"Received notification: {message.data}")

                    # Broadcast to session
                    notification_msg = WSMessage(
                        type="notification",
                        data=message.data,
                        session_id=session_id,
                    )
                    await manager.send_to_session(
                        notification_msg,
                        session_id or connection_id,
                    )

                else:
                    # Unknown message type
                    error_msg = WSMessage(
                        type="error",
                        data={
                            "message": f"Unknown message type: {message.type}",
                            "original_type": message.type,
                        },
                        session_id=session_id,
                    )
                    await manager.send_message(error_msg, connection_id)

            except Exception as e:
                logger.error(f"Error handling message: {e}")
                error_msg = WSMessage(
                    type="error",
                    data={"message": f"Error processing message: {str(e)}"},
                    session_id=session_id,
                )
                await manager.send_message(error_msg, connection_id)

    except WebSocketDisconnect:
        manager.disconnect(connection_id)
        logger.info(f"WebSocket disconnected: {connection_id}")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(connection_id)
