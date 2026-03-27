"""Pattern Memory implementation.

This module provides the main PatternMemory class that integrates
PatternNN and PatternExtractor for pattern storage, retrieval, and learning.
"""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import torch

from app.config import get_settings
from app.memory.auto_learning.extractor import PatternExtractor
from app.memory.auto_learning.models import Pattern, PatternExtractionResult
from app.memory.auto_learning.nn import PatternNN

if TYPE_CHECKING:
    from app.memory.auto_learning.reflection.models import LearningResult

logger = logging.getLogger(__name__)


class PatternMemory:
    """Main pattern memory class for storing and retrieving patterns.

    This class integrates PatternNN and PatternExtractor to provide:
    - Pattern extraction from execution records
    - Pattern storage and persistence
    - Pattern retrieval using neural network
    - Automatic learning and weight updates

    Attributes:
        nn: PatternNN neural network for pattern matching
        extractor: PatternExtractor for LLM-based pattern extraction
        embedder: SentenceTransformer for text embeddings
        patterns: List of stored patterns
        data_dir: Directory for data storage
    """

    def __init__(
        self,
        nn: PatternNN | None = None,
        extractor: PatternExtractor | None = None,
        embedder: SentenceTransformer | None = None,
        data_dir: Path | None = None,
    ) -> None:
        """Initialize PatternMemory.

        Args:
            nn: Optional PatternNN instance. If None, creates default.
            extractor: Optional PatternExtractor instance. If None, creates default.
            embedder: Optional SentenceTransformer instance. If None, creates default.
            data_dir: Optional data directory path. If None, uses default from settings.
        """
        self.settings = get_settings()
        self.data_dir = Path(data_dir or self.settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.nn = nn or PatternNN(
            embed_dim=384,  # all-MiniLM-L6-v2 embedding dimension
            num_patterns=64,
            learning_rate=1e-3,
            dropout=0.1,
        )

        self.extractor = extractor or PatternExtractor()

        # Initialize embedder - use miniclaw's embedding manager
        if embedder is not None:
            self.embedder = embedder
        else:
            # Lazy initialization - will get from embedding_manager when needed
            self.embedder = None
            self._embedding_manager = None

        # Load existing patterns
        self.patterns: list[Pattern] = []
        self._load_patterns()

        # Load NN weights if available
        self._load_nn_weights()

        logger.info(
            f"PatternMemory initialized with {len(self.patterns)} patterns, "
            f"data_dir={self.data_dir}"
        )

    async def extract_and_store(
        self,
        situation: str,
        outcome: str,
        fix: str,
    ) -> PatternExtractionResult:
        """Extract and store a pattern (main entry point).

        This method:
        1. Extracts a pattern using LLM
        2. Creates a Pattern object
        3. Adds it to the pattern list
        4. Trains the neural network
        5. Persists to disk

        Args:
            situation: Task context/situation description
            outcome: Execution result
            fix: Action taken to fix the issue

        Returns:
            PatternExtractionResult with extracted pattern and metadata

        Examples:
            >>> memory = PatternMemory()
            >>> result = await memory.extract_and_store(
            ...     situation="API timeout error",
            ...     outcome="Failed after 30s",
            ...     fix="Increased timeout to 60s"
            ... )
            >>> print(result.pattern)
            'API timeout: Increase timeout from 30s to 60s'
        """
        try:
            logger.info(f"Extracting pattern from situation: {situation[:50]}...")

            # Step 1: Extract pattern using LLM
            pattern_description = await self.extractor.extract(situation, outcome, fix)

            # Step 2: Create pattern object
            pattern_id = str(uuid.uuid4())[:8]
            pattern = Pattern(
                id=pattern_id,
                description=pattern_description,
                situation=situation,
                outcome=outcome,
                fix_action=fix,
            )

            # Step 3: Add to patterns list
            self.patterns.append(pattern)
            logger.info(f"Added pattern {pattern_id}: {pattern_description[:50]}...")

            # Step 4: Train neural network
            self._train_nn(pattern)

            # Step 5: Persist to disk
            self._save_patterns()
            self.nn.save()

            # Return extraction result
            return PatternExtractionResult(
                pattern=pattern_description,
                confidence=0.8,
                source_data={
                    "situation": situation,
                    "outcome": outcome,
                    "fix": fix,
                    "pattern_id": pattern_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to extract and store pattern: {e}", exc_info=True)
            # Return fallback result
            return PatternExtractionResult(
                pattern=f"Pattern: {situation[:100]} -> {fix[:100]}",
                confidence=0.5,
                source_data={"situation": situation, "outcome": outcome, "fix": fix},
            )

    def get_top_patterns(self, query: str, top_k: int = 3) -> list[dict[str, str | float]]:
        """Get top K patterns matching the query.

        Uses the neural network to find the most relevant patterns
        based on semantic similarity.

        Args:
            query: Query string to match against patterns
            top_k: Number of top patterns to return

        Returns:
            List of top matching patterns with metadata

        Examples:
            >>> memory = PatternMemory()
            >>> patterns = memory.get_top_patterns("API timeout", top_k=3)
            >>> for p in patterns:
            ...     print(f"{p['description']}: {p['similarity']:.2f}")
        """
        if not self.patterns:
            logger.warning("No patterns available for retrieval")
            return []

        try:
            # Generate embedding for query
            query_embedding = self._get_embedding(query)

            # Get predictions from neural network
            top_indices = self.nn.predict(query_embedding, top_k=top_k)

            # Convert to list and map to patterns
            results = []
            for idx in top_indices.tolist():
                if idx < len(self.patterns):
                    pattern = self.patterns[idx]
                    results.append(
                        {
                            "id": pattern.id,
                            "description": pattern.description,
                            "situation": pattern.situation,
                            "outcome": pattern.outcome,
                            "fix_action": pattern.fix_action,
                            "similarity": 0.8,  # Placeholder similarity score
                        }
                    )

            logger.info(f"Retrieved {len(results)} patterns for query: {query[:50]}...")
            return results

        except Exception as e:
            logger.error(f"Failed to retrieve patterns: {e}", exc_info=True)
            return []

    def _train_nn(self, pattern: Pattern) -> None:
        """Train neural network with new pattern.

        Args:
            pattern: Pattern to train with
        """
        try:
            # Generate embedding for pattern description
            embedding = self._get_embedding(pattern.description)

            # Get pattern index (label)
            pattern_idx = len(self.patterns) - 1

            # Ensure NN has enough output neurons
            if pattern_idx >= self.nn.num_patterns:
                logger.warning(
                    f"Pattern index {pattern_idx} exceeds NN capacity "
                    f"{self.nn.num_patterns}, skipping training"
                )
                return

            # Update NN with new pattern
            loss = self.nn.update(embedding, pattern_idx)
            logger.debug(
                f"Trained NN with pattern {pattern.id}, loss={loss:.4f}, "
                f"buffer_size={self.nn.get_buffer_size()}"
            )

        except Exception as e:
            logger.error(f"Failed to train NN: {e}", exc_info=True)

    def _load_patterns(self) -> None:
        """Load patterns from disk.

        Reads patterns from patterns.json file in the data directory.
        If the file doesn't exist, initializes with empty pattern list.
        """
        patterns_path = self.data_dir / "patterns.json"

        if not patterns_path.exists():
            logger.info(f"Patterns file not found: {patterns_path}, starting fresh")
            return

        try:
            with open(patterns_path, "r", encoding="utf-8") as f:
                patterns_data = json.load(f)

            # Deserialize patterns
            self.patterns = [
                Pattern(
                    id=p["id"],
                    description=p["description"],
                    situation=p["situation"],
                    outcome=p["outcome"],
                    fix_action=p["fix_action"],
                    created_at=datetime.fromisoformat(p["created_at"]),
                )
                for p in patterns_data
            ]

            logger.info(f"Loaded {len(self.patterns)} patterns from {patterns_path}")

        except Exception as e:
            logger.error(f"Failed to load patterns: {e}", exc_info=True)
            self.patterns = []

    def _save_patterns(self) -> None:
        """Save patterns to disk using atomic write.

        Writes patterns to patterns.json file in the data directory.
        Uses atomic write (temp file + rename) to prevent corruption.
        """
        patterns_path = self.data_dir / "patterns.json"

        try:
            # Serialize patterns
            patterns_data = [
                {
                    "id": p.id,
                    "description": p.description,
                    "situation": p.situation,
                    "outcome": p.outcome,
                    "fix_action": p.fix_action,
                    "created_at": p.created_at.isoformat(),
                }
                for p in self.patterns
            ]

            # Atomic write: save to temp file first, then rename
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".json", dir=self.data_dir
            ) as tmp_file:
                temp_path = Path(tmp_file.name)
                json.dump(patterns_data, tmp_file, indent=2, ensure_ascii=False)

            # Atomic rename
            temp_path.replace(patterns_path)

            logger.info(f"Saved {len(self.patterns)} patterns to {patterns_path}")

        except Exception as e:
            logger.error(f"Failed to save patterns: {e}", exc_info=True)
            raise IOError(f"Failed to save patterns to {patterns_path}: {e}") from e

    def _load_nn_weights(self) -> None:
        """Load neural network weights from disk.

        Loads weights from pattern_nn.pth file in the data directory.
        If the file doesn't exist, initializes with random weights.
        """
        nn_path = self.data_dir / "pattern_nn.pth"

        if not nn_path.exists():
            logger.info(f"NN weights file not found: {nn_path}, using random weights")
            return

        try:
            self.nn.load(nn_path)
            logger.info(f"Loaded NN weights from {nn_path}")

        except FileNotFoundError:
            logger.warning(f"NN weights file not found: {nn_path}")
        except Exception as e:
            logger.error(f"Failed to load NN weights: {e}", exc_info=True)

    def _get_embedding_manager(self):
        """Get miniclaw's embedding manager singleton."""
        if self._embedding_manager is None:
            from app.core.embedding_manager import get_embedding_manager
            self._embedding_manager = get_embedding_manager()
        return self._embedding_manager

    def _get_embedding(self, text: str) -> torch.Tensor:
        """Get embedding for text using miniclaw's embedding manager.

        Args:
            text: Text to embed

        Returns:
            Embedding tensor of shape (embed_dim,)

        Raises:
            RuntimeError: If embedding model is not ready
        """
        # Get or create embedding manager
        emb_manager = self._get_embedding_manager()

        # Get the embedding model
        model = emb_manager.get_model()
        if model is None:
            raise RuntimeError(
                "Embedding model not ready. Please ensure the embedding manager "
                "has been warmed up before using PatternMemory."
            )

        # Get embedding from LlamaIndex model
        # Note: HuggingFaceEmbedding returns list[float], need to convert to torch tensor
        embedding_list = model.get_text_embedding(text)
        embedding_tensor = torch.tensor(embedding_list, dtype=torch.float32)

        logger.debug(f"Generated embedding with shape: {embedding_tensor.shape}")
        return embedding_tensor


# Singleton instance
_pattern_memory_instance: PatternMemory | None = None


# Singleton instance
_pattern_memory_instance: PatternMemory | None = None


def get_pattern_memory() -> PatternMemory:
    """Get the global pattern memory instance.

    Returns:
        PatternMemory: Global pattern memory instance
    """
    global _pattern_memory_instance

    if _pattern_memory_instance is None:
        _pattern_memory_instance = PatternMemory()

    return _pattern_memory_instance


def reset_pattern_memory() -> None:
    """Reset the global pattern memory to force recreation on next access.

    This should be called when configuration is updated to ensure
    the new configuration is picked up immediately.
    """
    global _pattern_memory_instance
    _pattern_memory_instance = None


# Stage 2: Reflection-driven learning methods
async def extract_and_reflect(
    self,
    user_query: str,
    agent_output: str,
    tool_calls: list[dict],
    execution_time: float = 0.0,
) -> PatternExtractionResult:
    """Extract pattern and reflect on execution (Stage 2 enhanced method).

    This is an enhanced version of extract_and_store that includes
    reflection analysis. It:
    1. Analyzes execution using reflection engine
    2. Extracts pattern if needed
    3. Stores pattern with reflection metadata

    Args:
        user_query: Original user query
        agent_output: Agent's output response
        tool_calls: List of tool call records
        execution_time: Execution time in seconds

    Returns:
        PatternExtractionResult with reflection-enhanced metadata

    Examples:
        >>> memory = PatternMemory()
        >>> result = await memory.extract_and_reflect(
        ...     user_query="What is the weather?",
        ...     agent_output="The weather is sunny.",
        ...     tool_calls=[]
        ... )
    """
    try:
        # Import reflection components (lazy import to avoid circular dependency)
        from app.memory.auto_learning.reflection import (
            ReflectionEngine,
            get_pattern_learner,
        )

        logger.info(f"Extracting and reflecting on query: {user_query[:50]}...")

        # Step 1: Reflect on execution
        reflection_engine = ReflectionEngine()
        reflection = await reflection_engine.reflect(
            user_query=user_query,
            agent_output=agent_output,
            tool_calls=tool_calls,
            execution_time=execution_time,
        )

        # Step 2: Extract pattern if execution was problematic
        if not reflection.completed or reflection.problems:
            # Use original extract_and_store method
            situation = user_query
            outcome = agent_output
            fix = "; ".join(reflection.suggestions) if reflection.suggestions else "No fix"

            result = await self.extract_and_store(situation, outcome, fix)

            # Add reflection metadata to result
            result.source_data["reflection"] = reflection.to_dict()

            return result
        else:
            # No pattern needed for successful execution
            logger.info("Execution successful, no pattern extraction needed")
            return PatternExtractionResult(
                pattern="",
                confidence=1.0,
                source_data={
                    "reflection": reflection.to_dict(),
                    "message": "Execution successful, no pattern extracted",
                },
            )

    except Exception as e:
        logger.error(f"Failed to extract and reflect: {e}", exc_info=True)
        # Return fallback result
        return PatternExtractionResult(
            pattern=f"Pattern: {user_query[:100]} -> {agent_output[:100]}",
            confidence=0.5,
            source_data={
                "user_query": user_query,
                "agent_output": agent_output,
                "error": str(e),
            },
        )


async def learn_from_execution(
    self,
    session_id: str,
    user_query: str,
    agent_output: str,
    tool_calls: list[dict],
    execution_time: float = 0.0,
) -> LearningResult:
    """Learn from agent execution using reflection-driven learning (Stage 2).

    This is the main entry point for Stage 2 learning. It coordinates
    reflection, reward computation, pattern extraction, and training.

    Args:
        session_id: Session identifier
        user_query: Original user query
        agent_output: Agent's output response
        tool_calls: List of tool call records
        execution_time: Execution time in seconds

    Returns:
        LearningResult with reflection, reward, and pattern info

    Examples:
        >>> memory = PatternMemory()
        >>> result = await memory.learn_from_execution(
        ...     session_id="session_123",
        ...     user_query="What is the weather?",
        ...     agent_output="The weather is sunny.",
        ...     tool_calls=[]
        ... )
        >>> print(result.reward.total_reward)
        0.75
    """
    try:
        # Import PatternLearner (lazy import)
        from app.memory.auto_learning.reflection import get_pattern_learner

        logger.info(f"Learning from execution in session {session_id}")

        # Get pattern learner and delegate
        learner = get_pattern_learner()
        result = await learner.learn_from_execution(
            session_id=session_id,
            user_query=user_query,
            agent_output=agent_output,
            tool_calls=tool_calls,
            execution_time=execution_time,
        )

        # If pattern was extracted, store it
        if result.pattern_extracted and result.pattern_id:
            logger.info(f"Storing extracted pattern {result.pattern_id}")

            # Create pattern from reflection data
            pattern = Pattern(
                id=result.pattern_id,
                description="",  # Will be filled by extractor
                situation=user_query,
                outcome=agent_output,
                fix_action="; ".join(result.reflection.suggestions)
                if result.reflection.suggestions
                else "No fix",
            )

            # Add to patterns list (don't train NN here to avoid duplication)
            # The actual pattern description will be filled by the extractor
            # in the PatternLearner.learn_from_execution method

        return result

    except Exception as e:
        logger.error(f"Failed to learn from execution: {e}", exc_info=True)

        # Return fallback result
        from app.memory.auto_learning.reflection.models import LearningResult

        return LearningResult(
            session_id=session_id,
            reflection=ReflectionResult(
                completed=False,
                problems=["Learning failed"],
                suggestions=[],
                confidence=0.0,
            ),
            reward=RewardResult(
                total_reward=0.0,
                semantic_reward=0.0,
                shaping_reward=0.0,
            ),
            pattern_extracted=False,
            pattern_id=None,
            training_triggered=False,
        )


# Add methods to PatternMemory class
PatternMemory.extract_and_reflect = extract_and_reflect
PatternMemory.learn_from_execution = learn_from_execution
