"""
Embedding Model Status API

Provides endpoints for monitoring embedding model loading status.
"""

from fastapi import APIRouter
from app.core.embedding_manager import get_embedding_manager

router = APIRouter(tags=["embedding"])


@router.get("/status")
async def get_embedding_status():
    """
    Query embedding model loading status.

    Returns current status information about the embedding model, including:
    - status: Current state (not_started/loading/ready/failed)
    - load_duration: Time taken to load the model (seconds), if ready
    - error: Error message if loading failed
    - model_name: Name of the model, if ready

    ## Response Examples

    **Model loading in background:**
    ```json
    {
      "status": "loading",
      "load_duration": null,
      "error": null,
      "model_name": null
    }
    ```

    **Model loaded successfully:**
    ```json
    {
      "status": "ready",
      "load_duration": 15.23,
      "error": null,
      "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    }
    ```

    **Model loading failed:**
    ```json
    {
      "status": "failed",
      "load_duration": null,
      "error": "Loading timed out after 60s",
      "model_name": null
    }
    ```

    Returns:
        Status information dictionary
    """
    manager = get_embedding_manager()
    return manager.get_status()
