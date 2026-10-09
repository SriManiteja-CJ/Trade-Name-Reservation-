"""
pipeline/deterministic_gates.py
Stage ② — Deterministic Gates

Performs all checks that require NO LLM and must run even during an LLM outage:
  1. Exact duplicate check (F2) — queries TradeNameIndex for active names
  2. Lexicon hard block (F4 — severity=block) → signal: BLOCKED
  3. Lexicon review flag (F4 — severity=review) → signal: NEEDS_REVIEW
  4. F12 exemption — if skip_word_checks=True, steps 2 & 3 are skipped

The results are returned as a list of GateSignal objects consumed by Stage ⑤
(decision_policy.py). Stage ② never produces a final outcome; it produces signals.

Spec references:
  F2  — exact-duplicate check against active names; case/space insensitive;
         excludes the record being edited
  F4  — word checks: 7 categories, each with severity block|review|info
  F12 — skip word checks when name unchanged and only form/branch changed;
         exact-dup check (F2) is still performed (per Ambiguity #2 resolution:
         always run F2; skip only F4 lexicon checks)
  F21 — released/rejected available again: enforced by status=active filter in F2
  §3 Component ② — "Exact duplicate on normalized keys; lexicon match with
         variants and edit distance; NameComposer applies branch suffix, legal-form
         display and the F12 exemption"
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from index.repository import IndexEntry, TradeNameIndexRepository
from lexicon.repository import LexiconEntry, LexiconRepository
from pipeline.name_composer import ComposedName
from pipeline.normalizer import normalize_arabic, normalize_english


class SignalType(str, Enum):
    BLOCKED = "BLOCKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INFO = "INFO"


@dataclass
class GateSignal:
    """
    A single signal produced by Stage ②.
    Consumed by Stage ⑤ decision policy to produce the final outcome.

    Fields:
      signal_type:   BLOCKED | NEEDS_REVIEW | INFO
      source:        "exact_duplicate" | "lexicon" | ...
      category:      F4 category name or None
      severity:      "block" | "review" | "info" from lexicon
      matched_term:  The lexicon term or registry entry that triggered the signal
      reason_en:     Human-readable explanation (English) — used in response (N4)
      reason_ar:     Human-readable explanation (Arabic) — used in response (N4)
      fix_en:        Suggested fix (English) — used in response (E4)
      fix_ar:        Suggested fix (Arabic)
      similar_entry: The TradeNameIndex entry for similarity signals
    """
    signal_type: SignalType
    source: str
    category: Optional[str] = None
    severity: Optional[str] = None
    matched_term: Optional[str] = None
    reason_en: str = ""
    reason_ar: str = ""
    fix_en: str = ""
    fix_ar: str = ""
    similar_entry: Optional[IndexEntry] = None


# Category → legacy boolean field mapping (N9 — existing fields preserved)
CATEGORY_TO_LEGACY_FIELD: dict[str, str] = {
    "prohibited": "Prohibted",
    "profanity": "Profanity",
    "unfriendly": "Unfriendly",
    "special": "Special",
    "divine_name": "AllahNames",
    "location": "LocationNames",
    "family_name": "FamilyNames",
}

# Human-readable reason templates for gate signals (N4 — bilingual explanations)
_REASON_EXACT_DUP_EN = (
    "This trade name already exists in the registry as an active name."
)
_REASON_EXACT_DUP_AR = (
    "هذا الاسم التجاري موجود بالفعل في السجل كاسم نشط."
)
_FIX_EXACT_DUP_EN = "Please choose a different trade name."
_FIX_EXACT_DUP_AR = "يرجى اختيار اسم تجاري مختلف."


def _lexicon_reason_en(entry: LexiconEntry) -> str:
    cat_labels = {
        "prohibited": "prohibited word",
        "profanity": "profane or offensive word",
        "unfriendly": "unfriendly word",
        "special": "special reserved word",
        "divine_name": "divine or sacred name",
        "location": "geographic location name",
        "family_name": "reserved family name",
    }
    label = cat_labels.get(entry.category, entry.category)
    return (
        f"The name contains a {label}: \"{entry.term}\". "
        f"This word is not permitted in trade names."
    )


def _lexicon_reason_ar(entry: LexiconEntry) -> str:
    cat_labels_ar = {
        "prohibited": "كلمة محظورة",
        "profanity": "كلمة بذيئة أو مسيئة",
        "unfriendly": "كلمة غير لائقة",
        "special": "كلمة محجوزة خاصة",
        "divine_name": "اسم إلهي أو مقدس",
        "location": "اسم موقع جغرافي",
        "family_name": "اسم عائلة محجوز",
    }
    label = cat_labels_ar.get(entry.category, entry.category)
    return f"الاسم يحتوي على {label}: \"{entry.term}\". هذه الكلمة غير مسموح بها في الأسماء التجارية."


def _lexicon_fix_en(entry: LexiconEntry) -> str:
    return f"Remove or replace \"{entry.term}\" from the trade name."


def _lexicon_fix_ar(entry: LexiconEntry) -> str:
    return f"يرجى إزالة أو استبدال \"{entry.term}\" من الاسم التجاري."


class DeterministicGates:
    """
    Runs Stage ② gates for a single validation request.
    Instantiated per-request with repository dependencies injected.
    """

    def __init__(
        self,
        index_repo: TradeNameIndexRepository,
        lexicon_repo: LexiconRepository,
    ) -> None:
        self._index = index_repo
        self._lexicon = lexicon_repo

    async def run(
        self,
        composed: ComposedName,
        exclude_trade_name_id: Optional[int] = None,
    ) -> list[GateSignal]:
        """
        Run all deterministic gate checks.

        Args:
            composed:               Output from NameComposer (Stage ①+composer)
            exclude_trade_name_id:  ID of the record being edited (F2, Ambiguity #7)

        Returns:
            List of GateSignal objects. Empty list means no issues found.
            Signals are ordered: BLOCKED signals first, then NEEDS_REVIEW, then INFO.
        """
        signals: list[GateSignal] = []

        # -----------------------------------------------------------------
        # F2 — Exact duplicate check
        # Always run — even when F12 skip_word_checks=True
        # (Ambiguity #2 resolution: F2 is not a "word check"; always runs)
        # -----------------------------------------------------------------
        duplicates = await self._index.lookup_exact(
            normalized_ar=composed.normalized_ar,
            normalized_en=composed.normalized_en,
            exclude_trade_name_id=exclude_trade_name_id,
        )
        for dup in duplicates:
            signals.append(
                GateSignal(
                    signal_type=SignalType.BLOCKED,
                    source="exact_duplicate",
                    category=None,
                    severity="block",
                    matched_term=f"ID:{dup.trade_name_id}",
                    reason_en=_REASON_EXACT_DUP_EN,
                    reason_ar=_REASON_EXACT_DUP_AR,
                    fix_en=_FIX_EXACT_DUP_EN,
                    fix_ar=_FIX_EXACT_DUP_AR,
                    similar_entry=dup,
                )
            )

        # -----------------------------------------------------------------
        # F4 — Lexicon word checks
        # Skipped if F12 exemption applies (skip_word_checks=True)
        # Checks both Arabic and English forms of the name
        # -----------------------------------------------------------------
        if not composed.skip_word_checks:
            # Check Arabic name against AR and "both" entries
            ar_signals = await self._check_lexicon(
                composed.normalized_ar, "ar"
            )
            # Check English name against EN and "both" entries
            en_signals = await self._check_lexicon(
                composed.normalized_en, "en"
            )
            signals.extend(ar_signals)
            signals.extend(en_signals)
        # If skip_word_checks=True: F4 checks skipped per F12 exemption.
        # F3 (similarity) is still performed in Stage ③ — not here.

        # Sort: BLOCKED first, then NEEDS_REVIEW, then INFO
        order = {SignalType.BLOCKED: 0, SignalType.NEEDS_REVIEW: 1, SignalType.INFO: 2}
        signals.sort(key=lambda s: order.get(s.signal_type, 99))
        return signals

    async def _check_lexicon(
        self, normalized_text: str, lang: str
    ) -> list[GateSignal]:
        """
        Check a normalized name text against all lexicon entries for the given lang.

        For each lexicon entry, checks if the normalized_term (or any variant)
        appears in the normalized_text using:
          1. Substring containment (exact occurrence within the name)
          2. RapidFuzz edit-distance match (handled inside LexiconRepository.find_matches)

        Returns GateSignals for each matching entry.
        """
        # Get all potentially matching entries via the repository
        # (repository handles fuzzy matching against variants)
        entries = await self._lexicon.find_matches(normalized_text, lang)

        signals: list[GateSignal] = []
        for entry in entries:
            # Skip entries without human approval (pending proposals)
            if entry.approved_by is None:
                continue

            if entry.severity == "block":
                sig_type = SignalType.BLOCKED
            elif entry.severity == "review":
                sig_type = SignalType.NEEDS_REVIEW
            else:
                sig_type = SignalType.INFO

            signals.append(
                GateSignal(
                    signal_type=sig_type,
                    source="lexicon",
                    category=entry.category,
                    severity=entry.severity,
                    matched_term=entry.term,
                    reason_en=_lexicon_reason_en(entry),
                    reason_ar=_lexicon_reason_ar(entry),
                    fix_en=_lexicon_fix_en(entry),
                    fix_ar=_lexicon_fix_ar(entry),
                )
            )

        return signals
