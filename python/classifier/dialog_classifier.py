"""
dialog_classifier.py — Auto-classify dialog events as NPC / SIGN / OBJECT / GIFT.

Uses a two-tier system:
  1. ptr_EBC exact match in fingerprint DB  -> high confidence (>=0.95)
  2. ptr_EB8 handler hint (script cmd type)  -> medium confidence
  3. UNKNOWN if neither matches              -> low confidence, needs calibration

Evidence base (47 calibration samples):
  - ptr_EB8 = 0x081A4E51 (BG_EVENT):    PURE NON-NPC (13/13)
  - ptr_EB8 = 0x081A4E47 (SCRIPT_CTX):  MIXED        (7: 6 NPC, 1 OBJECT)
  - ptr_EB8 = 0x081A4E5A (OBJ_EVENT):   MIXED        (20: 13 NPC, 7 non-NPC)
  - ptr_EB8 = 0x081A4E62 (SPECIAL_EVT): MIXED        (5: 1 NPC, 4 non-NPC)
  - ptr_EB8 = 0x081A658C (NPC_SPECIAL): PURE NPC     (1: Nurse Joy)
  - ptr_EB8 = 0x081A6817 (ITEM_PICKUP): PURE NON-NPC (1: found item)
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# Types

VALID_KINDS = ("NPC", "SIGN", "OBJECT", "GIFT", "UNKNOWN")

# Known ptr_EB8 script command handler addresses (ROM)
EB8_HANDLERS: dict[str, str] = {
    "0x081A4E51": "BG_EVENT",      # Background event: signs, objects, env tiles (13 samples)
    "0x081A4E5A": "OBJ_EVENT",     # Object event: NPCs, boards, PCs, etc. (20 samples)
    "0x081A4E47": "SCRIPT_CTX",    # Script context: mostly NPC, 1 object exception (7 samples)
    "0x081A4E62": "SPECIAL_EVT",   # Special event: starter select, naming, misc (5 samples)
    "0x081A658C": "NPC_SPECIAL",   # Special NPC handler: Nurse Joy type (1 sample)
    "0x081A6817": "ITEM_PICKUP",   # Found item on ground: pokeball items (1 sample)
}

# What ptr_EB8 handler types imply about NPC likelihood
EB8_NPC_HINT: dict[str, tuple[bool, float]] = {
    "BG_EVENT":     (False, 0.95),  # PURE NON-NPC: 0/13
    "SCRIPT_CTX":   (True,  0.70),  # MOSTLY NPC: 6/7
    "OBJ_EVENT":    (True,  0.40),  # MIXED: 13 NPC / 7 non-NPC
    "SPECIAL_EVT":  (False, 0.35),  # MIXED: 1 NPC / 4 non-NPC
    "NPC_SPECIAL":  (True,  0.80),  # PURE NPC: 1/1
    "ITEM_PICKUP":  (False, 0.90),  # PURE NON-NPC: 1/1
}


@dataclass
class Classification:
    """Result of classifying a dialog_open event."""
    result: str           # NPC, SIGN, OBJECT, GIFT, UNKNOWN
    confidence: float     # 0.0 to 1.0
    fingerprint_primary: str | None = None    # ptr_EBC value
    fingerprint_secondary: str | None = None  # ptr_EB8 value
    handler_type: str = "UNKNOWN_HANDLER"
    evidence: list[str] = field(default_factory=list)
    is_known: bool = False
    needs_calibration: bool = False

    def to_dict(self) -> dict:
        return {
            "type": "classification",
            "result": self.result,
            "confidence": round(self.confidence, 2),
            "fingerprint_primary": self.fingerprint_primary,
            "fingerprint_secondary": self.fingerprint_secondary,
            "handler_type": self.handler_type,
            "is_known": self.is_known,
            "needs_calibration": self.needs_calibration,
            "evidence": self.evidence,
        }


# Classifier

class DialogClassifier:
    """
    Classifies dialog_open events using fingerprint DB and ptr_EB8 hints.

    Usage:
        classifier = DialogClassifier("data/fingerprints/pallet_town/fingerprints.json")
        result = classifier.classify(ptr_ebc="0x08165837", ptr_eb8="0x081A4E47")
        print(result.result, result.confidence)
    """

    def __init__(self, db_path: str | Path = "fingerprint_db.json"):
        self.db_path = Path(db_path)
        self.db: dict[str, dict] = {}
        self.load_db()

    def load_db(self):
        """Load fingerprint DB from disk."""
        if self.db_path.exists():
            with open(self.db_path, "r", encoding="utf-8") as f:
                self.db = json.load(f)
        else:
            self.db = {}

    def reload(self):
        """Reload DB from disk (call after calibration adds new entries)."""
        self.load_db()

    @property
    def known_count(self) -> int:
        return len(self.db)

    def classify(self, ptr_ebc: str, ptr_eb8: str) -> Classification:
        """
        Classify a dialog_open event.

        Parameters
        ----------
        ptr_ebc : str
            Value of 0x03000EBC as hex string (e.g. "0x08165837").
        ptr_eb8 : str
            Value of 0x03000EB8 as hex string (e.g. "0x081A4E47").

        Returns
        -------
        Classification
        """
        handler_type = EB8_HANDLERS.get(ptr_eb8, "UNKNOWN_HANDLER")
        evidence: list[str] = []

        # Tier 1: Exact fingerprint match (ptr_EBC in DB)
        if ptr_ebc in self.db:
            entry = self.db[ptr_ebc]
            kind = entry["kind"]
            label = entry.get("label", "?")
            evidence.append(
                f"ptr_EBC {ptr_ebc} found in fingerprint DB: "
                f"{kind} (label: {label})"
            )
            evidence.append(f"ptr_EB8 handler: {ptr_eb8} = {handler_type}")
            return Classification(
                result=kind,
                confidence=0.95,
                fingerprint_primary=ptr_ebc,
                fingerprint_secondary=ptr_eb8,
                handler_type=handler_type,
                evidence=evidence,
                is_known=True,
                needs_calibration=False,
            )

        # Tier 2: ptr_EB8 handler hint
        if handler_type in EB8_NPC_HINT:
            is_npc_likely, hint_confidence = EB8_NPC_HINT[handler_type]

            if handler_type == "BG_EVENT":
                evidence.append(
                    f"ptr_EB8 {ptr_eb8} = BG_EVENT -> PURE NON-NPC (0/13)"
                )
                evidence.append(f"ptr_EBC {ptr_ebc} NOT in DB — needs calibration")
                return Classification(
                    result="SIGN",
                    confidence=hint_confidence,
                    fingerprint_primary=ptr_ebc,
                    fingerprint_secondary=ptr_eb8,
                    handler_type=handler_type,
                    evidence=evidence,
                    is_known=False,
                    needs_calibration=True,
                )

            elif handler_type == "ITEM_PICKUP":
                evidence.append(
                    f"ptr_EB8 {ptr_eb8} = ITEM_PICKUP -> found item on ground"
                )
                evidence.append(f"ptr_EBC {ptr_ebc} NOT in DB")
                return Classification(
                    result="GIFT",
                    confidence=hint_confidence,
                    fingerprint_primary=ptr_ebc,
                    fingerprint_secondary=ptr_eb8,
                    handler_type=handler_type,
                    evidence=evidence,
                    is_known=False,
                    needs_calibration=True,
                )

            elif handler_type == "NPC_SPECIAL":
                evidence.append(
                    f"ptr_EB8 {ptr_eb8} = NPC_SPECIAL -> Nurse Joy type NPC"
                )
                evidence.append(f"ptr_EBC {ptr_ebc} NOT in DB — needs calibration")
                return Classification(
                    result="NPC",
                    confidence=hint_confidence,
                    fingerprint_primary=ptr_ebc,
                    fingerprint_secondary=ptr_eb8,
                    handler_type=handler_type,
                    evidence=evidence,
                    is_known=False,
                    needs_calibration=True,
                )

            elif handler_type == "SCRIPT_CTX":
                evidence.append(
                    f"ptr_EB8 {ptr_eb8} = SCRIPT_CTX -> mostly NPC (6/7)"
                )
                evidence.append(f"ptr_EBC {ptr_ebc} NOT in DB — needs calibration")
                return Classification(
                    result="NPC",
                    confidence=hint_confidence,
                    fingerprint_primary=ptr_ebc,
                    fingerprint_secondary=ptr_eb8,
                    handler_type=handler_type,
                    evidence=evidence,
                    is_known=False,
                    needs_calibration=True,
                )

            elif handler_type == "OBJ_EVENT":
                evidence.append(
                    f"ptr_EB8 {ptr_eb8} = OBJ_EVENT -> MIXED (13 NPC / 7 non-NPC)"
                )
                evidence.append(f"ptr_EBC {ptr_ebc} NOT in DB — needs calibration")
                return Classification(
                    result="UNKNOWN",
                    confidence=0.30,
                    fingerprint_primary=ptr_ebc,
                    fingerprint_secondary=ptr_eb8,
                    handler_type=handler_type,
                    evidence=evidence,
                    is_known=False,
                    needs_calibration=True,
                )

            elif handler_type == "SPECIAL_EVT":
                evidence.append(
                    f"ptr_EB8 {ptr_eb8} = SPECIAL_EVT -> mixed-nonNPC (1/5)"
                )
                evidence.append(f"ptr_EBC {ptr_ebc} NOT in DB — needs calibration")
                return Classification(
                    result="UNKNOWN",
                    confidence=0.35,
                    fingerprint_primary=ptr_ebc,
                    fingerprint_secondary=ptr_eb8,
                    handler_type=handler_type,
                    evidence=evidence,
                    is_known=False,
                    needs_calibration=True,
                )

        # Tier 3: Completely unknown ──
        evidence.append(f"ptr_EB8 {ptr_eb8} = UNKNOWN handler")
        evidence.append(f"ptr_EBC {ptr_ebc} NOT in fingerprint DB")
        evidence.append("No classification possible — full calibration needed")
        return Classification(
            result="UNKNOWN",
            confidence=0.10,
            fingerprint_primary=ptr_ebc,
            fingerprint_secondary=ptr_eb8,
            handler_type=handler_type,
            evidence=evidence,
            is_known=False,
            needs_calibration=True,
        )

    def add_fingerprint(self, ptr_ebc: str, kind: str, label: str,
                        ptr_eb8: str = "", sample_text: str = "",
                        notes: str = "") -> None:
        """Add a new fingerprint to the DB and save to disk."""
        if kind not in VALID_KINDS or kind == "UNKNOWN":
            raise ValueError(f"Invalid kind: {kind!r}. Use one of: {VALID_KINDS[:-1]}")
        self.db[ptr_ebc] = {
            "kind": kind,
            "label": label,
            "ptr_EB8_observed": ptr_eb8,
            "sample_text": sample_text[:60],
            "notes": notes,
        }
        self._save()

    def _save(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.db, f, indent=2, ensure_ascii=False)

    def stats(self) -> dict[str, int]:
        """Return count of each kind in the DB."""
        counts: dict[str, int] = {}
        for entry in self.db.values():
            k = entry.get("kind", "?")
            counts[k] = counts.get(k, 0) + 1
        return counts


# Quick test

if __name__ == "__main__":
    c = DialogClassifier()

    print(f"Loaded {c.known_count} fingerprints")
    print(f"Stats: {c.stats()}\n")

    r = c.classify(ptr_ebc="0x08165837", ptr_eb8="0x081A4E47")
    print(f"Test 1 (known NPC):   {r.result} conf={r.confidence} known={r.is_known}")
    for e in r.evidence:
        print(f"  - {e}")

    print()

    r = c.classify(ptr_ebc="0x08FFFFFF", ptr_eb8="0x081A4E51")
    print(f"Test 2 (unknown, BG): {r.result} conf={r.confidence} needs_cal={r.needs_calibration}")
    for e in r.evidence:
        print(f"  - {e}")
