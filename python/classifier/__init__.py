"""
classifier — Dialog event classification (NPC / SIGN / OBJECT / GIFT).

Uses fingerprint DB + ptr_EB8 handler hints.
"""

from .dialog_classifier import (
    DialogClassifier,
    Classification,
    VALID_KINDS,
    EB8_HANDLERS,
    EB8_NPC_HINT,
)

__all__ = [
    "DialogClassifier",
    "Classification",
    "VALID_KINDS",
    "EB8_HANDLERS",
    "EB8_NPC_HINT",
]
