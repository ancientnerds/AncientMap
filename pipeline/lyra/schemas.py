"""JSON schemas for structured output enforcement in the research pipeline.

Every claim-producing LLM call uses one of these schemas via structured_llm_call().
All claim objects require source_ids — no silent drops.
"""

DECOMPOSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "original_question": {"type": "string"},
        "extracted_topic": {"type": "string"},
        "extracted_hypothesis": {"type": ["string", "null"]},
        "angles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "topic": {"type": "string"},
                    "description": {"type": "string"},
                    "search_queries": {"type": "array", "items": {"type": "string"}},
                    "specialist_domains": {"type": "array", "items": {"type": "string"}},
                    "category": {"type": "string"},
                },
                "required": [
                    "id",
                    "topic",
                    "description",
                    "search_queries",
                    "specialist_domains",
                ],
            },
        },
    },
    "required": ["angles"],
}

SPECIALIST_FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "evidence": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": ["claim", "evidence", "source_ids", "confidence"],
            },
        },
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["findings"],
}

SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "consensus_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "supporting_specialists": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string"},
                },
                "required": ["claim", "source_ids"],
            },
        },
        "contested_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "for": {"type": "object"},
                    "against": {"type": "object"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim"],
            },
        },
        "unique_insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "specialist": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string"},
                },
                "required": ["claim", "source_ids"],
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "consensus_claims",
        "contested_claims",
        "unique_insights",
        "open_questions",
    ],
}

CROSS_ANGLE_SCHEMA = {
    "type": "object",
    "properties": {
        "convergent_findings": {"type": "array", "items": {"type": "object"}},
        "contradictions": {"type": "array", "items": {"type": "object"}},
        "connections": {"type": "array", "items": {"type": "object"}},
        "gaps": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["convergent_findings", "connections"],
}

DEBATE_CHALLENGE_SCHEMA = {
    "type": "object",
    "properties": {
        "strengthening_suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_claim": {"type": "string"},
                    "target_specialist": {"type": "string"},
                    "suggestion_type": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "evidence": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["target_claim", "suggestion", "source_ids"],
            },
        },
    },
    "required": ["strengthening_suggestions"],
}

DEBATE_DEFENSE_SCHEMA = {
    "type": "object",
    "properties": {
        "incorporations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "suggestion_id": {"type": "integer"},
                    "response": {
                        "type": "string",
                        "enum": ["accept", "note", "decline"],
                    },
                    "argument": {"type": "string"},
                    "additional_evidence": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["response", "argument"],
            },
        },
    },
    "required": ["incorporations"],
}

MODERATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "final_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "confidence": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["claim", "source_ids"],
            },
        },
        "revised_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "revised": {"type": "string"},
                    "reason": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["revised", "source_ids"],
            },
        },
        "speculative_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "confidence": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                    "what_would_strengthen": {"type": "string"},
                },
                "required": ["claim", "source_ids"],
            },
        },
        "dropped_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["claim", "reason"],
            },
        },
    },
    "required": [
        "final_claims",
        "revised_claims",
        "speculative_claims",
        "dropped_claims",
    ],
}

CROSS_POLLINATION_SCHEMA = {
    "type": "object",
    "properties": {
        "cross_pollination": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "angle_id": {"type": "string"},
                    "enriched_queries": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "cross_insights": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["angle_id", "enriched_queries"],
            },
        },
        "convergent_patterns": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["cross_pollination"],
}
