"""Detection package — cross-cutting, pure-Python pattern detection.

All detectors in this package:
- Are pure functions (no FastAPI / Pydantic / request objects)
- Return ``DetectionResult`` with a confidence score
- Log scores, decisions, and conflicts via ``log_detection``
- Are reusable across any layer of the application
"""

from src.detection.base import DetectionResult, score_phrases, log_detection

__all__ = ["DetectionResult", "score_phrases", "log_detection"]
