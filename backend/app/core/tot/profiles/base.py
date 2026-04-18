"""
Base Domain Profile Model.

Defines the schema for domain-specific evaluation profiles used by
the ToT framework to tailor reasoning, scoring, and stopping criteria.
"""

from pydantic import BaseModel
from typing import Any, Dict, List


class DomainProfile(BaseModel):
    """
    A domain-specific profile that configures ToT reasoning behavior.

    Each profile defines scoring dimensions, fatal flaws to watch for,
    preferred reasoning methods, and output constraints tailored to
    a specific task domain.

    Attributes:
        task: Human-readable task domain name.
        goal: High-level goal description for this domain.
        must_check: Critical validation points that must be verified.
        preferred_methods: Reasoning methods preferred in this domain.
        fatal_flaws: Patterns that indicate a thought is irrecoverably bad.
        scoring_dimensions: Mapping of dimension name to description.
        weights: Mapping of dimension name to weight (must sum to 1.0).
        stop_condition_signals: Signals mapped to indicator strings for
            early termination detection.
        confidence_calibration_rules: Rules for adjusting confidence scores.
        output_requirements: Mandatory elements in the final output.
        style_constraints: Formatting and style requirements.
    """

    task: str
    goal: str
    must_check: List[str] = []
    preferred_methods: List[str] = []
    fatal_flaws: List[str] = []
    scoring_dimensions: Dict[str, str] = {}
    weights: Dict[str, float] = {}
    stop_condition_signals: Dict[str, List[str]] = {}
    confidence_calibration_rules: List[Dict[str, str]] = []
    output_requirements: List[str] = []
    style_constraints: List[str] = []

    # Domain-specific generator behavior instructions (injected into system prompt)
    generator_instruction: str = ""

    # Domain-specific evaluator behavior instructions (injected into system prompt)
    evaluator_instruction: str = ""

    # Domain-specific termination/final answer instructions
    termination_instruction: str = ""

    # Domain-specific synthesis instructions (injected into synthesis node)
    synthesis_instruction: str = ""

    # Tools that this domain REQUIRES to be called (enforced in generation + termination)
    required_tools: List[str] = []

    # Domain-specific output JSON Schema (injected into Final Writer)
    preferred_output_schema: Dict[str, Any] = {}
