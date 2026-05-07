"""Semantic detection sub-package.

Provides concept mapping and synonym expansion as pure-Python, scored
detectors.
"""

from src.detection.semantic.concept_mapper import ConceptRule, map_concepts, ONTOLOGY
from src.detection.semantic.synonym_expander import expand, SYNONYMS

__all__ = [
    "ConceptRule",
    "map_concepts",
    "ONTOLOGY",
    "expand",
    "SYNONYMS",
]
