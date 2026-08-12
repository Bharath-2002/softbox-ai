"""LLM-driven orchestrators.

Deterministic Python control flow that calls model ports and validates
structured output: template analysis, QC review, copywriting. Agents never
touch a provider SDK directly - they go through ports.

May import: features, services, entities, shared.
"""
