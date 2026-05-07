"""Classification detection sub-package.

Exports all classifier functions.
"""

from src.detection.classification.page_purpose_classifier import classify_page_purpose
from src.detection.classification.template_classifier import classify_template

__all__ = ["classify_page_purpose", "classify_template"]
