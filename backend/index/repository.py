"""
index/repository.py
TradeNameIndex async repository.

Provides all query operations needed by:
  Stage ② — lookup_exact (F2 exact duplicate check)
  Stage ③ — lookup_phonetic, lookup_trigram, lookup_vector (F3 similarity search)
  Stage ⑦ — upsert, delete (F15 index sync)
  GET Search endpoint — lookup_trigram + lookup_vector (F19, E8)

All queries filter to status='active' by default (F2, F3, F21).
F21: Released/rejected names are excluded because they have status != 'active'.
     The sync worker sets status appropriately when a name is released/deleted.

Spec references:
  F2  — exact duplicate against active names, ignoring case/spaces, excl. current
  F3  — similarity check against existing names
  F15 — index stays in sync on insert, edit, release, delete
  F19 — keyword search over trade names
  F21 — rejected or released names become available (filtered out by status)
  E2  — phonetic + embedding matching
  E8  — fuzzy, cross-language search
  §5.1 — TradeNameIndex table

NOTE on embeddings: SQLAlchemy does not natively support pgvector's VECTOR type.
Vector operations use sqlalchemy text() with explicit SQL. The column is stored
as TEXT in the ORM model and cast with ::vector in queries (see Alembic migration
for the actual VECTOR(N) column definition).
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TradeNameIndex

ACTIVE_STATUS = "active"


@dataclass
class IndexEntry:
    """Lightweight DTO for a TradeNameIndex row."""
    id: int
    trade_name_id: int
    normalized_ar: str
    normalized_en: str
    phonetic_key: str
    category_id: Optional[int]
    status: str
    similarity_score: float = 0.0  # populated by similarity queries


class TradeNameIndexRepository:
    """
    Async repository for TradeNameIndex operations.
    Injected with an AsyncSession per request.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # Stage ② — Exact duplicate check (F2)
    # -----------------------------------------------------------------------
    async def lookup_exact(
        self,
        normalized_ar: str,
        normalized_en: str,
        exclude_trade_name_id: Optional[int] = None,
    ) -> list[IndexEntry]:
        """
        Check for exact duplicates against ACTIVE names.
        Spec F2: "Exact-duplicate check against active names (not released, not
        expired, not draft), ignoring case and spaces, excluding the record being edited."

        The normalizer already handles case-folding and whitespace; the
        comparison is done on normalized forms.

        Args:
            normalized_ar:          Normalized Arabic name from Stage ①
            normalized_en:          Normalized English name from Stage ①
            exclude_trade_name_id:  trade_name_id of the record being edited
                                    (Ambiguity #7: caller provides this for edit/renew)

        Returns:
            List of IndexEntry objects that are exact matches (should be empty for OK).
        """
        norm_ar_clean = normalized_ar.strip() if normalized_ar else ""
        norm_en_clean = normalized_en.strip().lower() if normalized_en else ""

        conditions = []
        params = {"status": ACTIVE_STATUS}

        if norm_ar_clean:
            conditions.append("TRIM(normalized_ar) = :norm_ar")
            params["norm_ar"] = norm_ar_clean
        if norm_en_clean:
            conditions.append("LOWER(TRIM(normalized_en)) = :norm_en")
            params["norm_en"] = norm_en_clean

        if not conditions:
            return []

        match_clause = " OR ".join(conditions)
        exclude_clause = "AND trade_name_id != :exclude_id" if exclude_trade_name_id is not None else ""
        sql = f"""
            SELECT id, trade_name_id, normalized_ar, normalized_en, phonetic_key,
                   category_id, status
            FROM trade_name_index
            WHERE status = :status
              AND ({match_clause})
              {exclude_clause}
        """
        if exclude_trade_name_id is not None:
            params["exclude_id"] = exclude_trade_name_id

        result = await self._session.execute(text(sql), params)
        rows = result.fetchall()
        return [
            IndexEntry(
                id=r[0],
                trade_name_id=r[1],
                normalized_ar=r[2],
                normalized_en=r[3],
                phonetic_key=r[4],
                category_id=r[5],
                status=r[6],
            )
            for r in rows
        ]

    # -----------------------------------------------------------------------
    # Stage ③ — Phonetic lookup (E2)
    # -----------------------------------------------------------------------
    async def lookup_phonetic(
        self,
        phonetic_key: str,
        exclude_trade_name_id: Optional[int] = None,
        limit: int = 10,
    ) -> list[IndexEntry]:
        """
        Find active names that share the phonetic key (or prefix thereof).
        Used for cross-script phonetic matching (E2: Noor = Nour = النور).

        The phonetic_key format is "{AR_KEY}|{EN_KEY}"; we search on both
        halves to allow Arabic query → English result and vice versa.
        """
        exclude_clause = "AND trade_name_id != :exclude_id" if exclude_trade_name_id is not None else ""
        sql = f"""
            SELECT id, trade_name_id, normalized_ar, normalized_en, phonetic_key,
                   category_id, status
            FROM trade_name_index
            WHERE status = :status
              AND (phonetic_key = :key OR phonetic_key LIKE :key_prefix)
              {exclude_clause}
            LIMIT :lim
        """
        # Also search for partial key matches (AR key only or EN key only)
        key_parts = phonetic_key.split("|")
        key_prefix = f"{key_parts[0]}|%" if len(key_parts) > 1 else f"{phonetic_key}|%"

        params = {
            "status": ACTIVE_STATUS,
            "key": phonetic_key,
            "key_prefix": key_prefix,
            "lim": limit,
        }
        if exclude_trade_name_id is not None:
            params["exclude_id"] = exclude_trade_name_id

        result = await self._session.execute(text(sql), params)
        rows = result.fetchall()
        return [
            IndexEntry(
                id=r[0],
                trade_name_id=r[1],
                normalized_ar=r[2],
                normalized_en=r[3],
                phonetic_key=r[4],
                category_id=r[5],
                status=r[6],
                similarity_score=0.9,  # phonetic match gets high base score
            )
            for r in rows
        ]

    # -----------------------------------------------------------------------
    # Stage ③ — Trigram similarity (pg_trgm) — used in Phase 1 Search
    # -----------------------------------------------------------------------
    async def lookup_trigram(
        self,
        normalized_ar: str,
        normalized_en: str,
        exclude_trade_name_id: Optional[int] = None,
        limit: int = 10,
    ) -> list[IndexEntry]:
        """
        Find similar active names using pg_trgm similarity.
        Returns results ordered by combined AR+EN similarity score.
        Used by Stage ③ (trigram signal) and GET Search in Phase 1.
        """
        norm_ar_clean = normalized_ar.strip() if normalized_ar else ""
        norm_en_clean = normalized_en.strip().lower() if normalized_en else ""

        exclude_clause = "AND trade_name_id != :exclude_id" if exclude_trade_name_id is not None else ""
        sql = f"""
            SELECT id, trade_name_id, normalized_ar, normalized_en, phonetic_key,
                   category_id, status,
                   GREATEST(
                       CASE WHEN :norm_ar != '' AND TRIM(normalized_ar) = :norm_ar THEN 1.0
                            WHEN :norm_ar != '' THEN similarity(normalized_ar, :norm_ar)
                            ELSE 0.0 END,
                       CASE WHEN :norm_en != '' AND LOWER(TRIM(normalized_en)) = :norm_en THEN 1.0
                            WHEN :norm_en != '' THEN similarity(normalized_en, :norm_en)
                            ELSE 0.0 END
                   ) AS sim_score
            FROM trade_name_index
            WHERE status = :status
              AND (
                  (:norm_ar != '' AND (TRIM(normalized_ar) = :norm_ar OR similarity(normalized_ar, :norm_ar) > 0.2))
                  OR (:norm_en != '' AND (LOWER(TRIM(normalized_en)) = :norm_en OR similarity(normalized_en, :norm_en) > 0.2))
              )
              {exclude_clause}
            ORDER BY sim_score DESC
            LIMIT :lim
        """
        params = {
            "status": ACTIVE_STATUS,
            "norm_ar": norm_ar_clean,
            "norm_en": norm_en_clean,
            "lim": limit,
        }
        if exclude_trade_name_id is not None:
            params["exclude_id"] = exclude_trade_name_id

        try:
            result = await self._session.execute(text(sql), params)
            rows = result.fetchall()
            return [
                IndexEntry(
                    id=r[0],
                    trade_name_id=r[1],
                    normalized_ar=r[2],
                    normalized_en=r[3],
                    phonetic_key=r[4],
                    category_id=r[5],
                    status=r[6],
                    similarity_score=float(r[7]),
                )
                for r in rows
            ]
        except Exception:
            # Fallback for testing environments without pg_trgm extension
            from rapidfuzz import fuzz
            sql_fallback = f"""
                SELECT id, trade_name_id, normalized_ar, normalized_en, phonetic_key,
                       category_id, status
                FROM trade_name_index
                WHERE status = :status
                  {exclude_clause}
            """
            fallback_params = {"status": ACTIVE_STATUS}
            if exclude_trade_name_id is not None:
                fallback_params["exclude_id"] = exclude_trade_name_id
            result = await self._session.execute(text(sql_fallback), fallback_params)
            rows = result.fetchall()
            scored: list[IndexEntry] = []
            for r in rows:
                score_ar = 0.0
                if norm_ar_clean and r[2]:
                    r2_clean = r[2].strip()
                    if norm_ar_clean == r2_clean:
                        score_ar = 1.0
                    else:
                        r_edit = fuzz.ratio(norm_ar_clean, r2_clean) / 100.0
                        r_sort = fuzz.token_sort_ratio(norm_ar_clean, r2_clean) / 100.0
                        score_ar = max(r_edit, r_sort)

                score_en = 0.0
                if norm_en_clean and r[3]:
                    r3_clean = r[3].strip().lower()
                    if norm_en_clean == r3_clean:
                        score_en = 1.0
                    else:
                        r_edit = fuzz.ratio(norm_en_clean, r3_clean) / 100.0
                        r_sort = fuzz.token_sort_ratio(norm_en_clean, r3_clean) / 100.0
                        score_en = max(r_edit, r_sort)

                max_score = max(score_ar, score_en)
                if max_score > 0.2:
                    scored.append(
                        IndexEntry(
                            id=r[0],
                            trade_name_id=r[1],
                            normalized_ar=r[2],
                            normalized_en=r[3],
                            phonetic_key=r[4],
                            category_id=r[5],
                            status=r[6],
                            similarity_score=float(max_score),
                        )
                    )
            scored.sort(key=lambda e: e.similarity_score, reverse=True)
            return scored[:limit]

    # -----------------------------------------------------------------------
    # Stage ③ — Vector similarity (pgvector cosine) — used in Phase 2+
    # -----------------------------------------------------------------------
    async def lookup_vector(
        self,
        embedding: list[float],
        lang: str,
        exclude_trade_name_id: Optional[int] = None,
        limit: int = 10,
    ) -> list[IndexEntry]:
        """
        Find similar active names using cosine similarity on pgvector embeddings.
        lang: "ar" uses embedding_ar column; "en" uses embedding_en column.

        Used by Stage ③ (embedding signal) when Ai.Search = shadow/on.
        If embeddings are not yet computed for an entry, it is silently skipped.
        """
        col = "embedding_ar" if lang == "ar" else "embedding_en"
        # Build embedding literal: '[0.1, 0.2, ...]'
        vec_literal = "[" + ",".join(str(v) for v in embedding) + "]"
        exclude_clause = "AND trade_name_id != :exclude_id" if exclude_trade_name_id is not None else ""
        sql = f"""
            SELECT id, trade_name_id, normalized_ar, normalized_en, phonetic_key,
                   category_id, status,
                   1 - ({col} <=> :vec::vector) AS cos_sim
            FROM trade_name_index
            WHERE status = :status
              AND {col} IS NOT NULL
              {exclude_clause}
            ORDER BY {col} <=> :vec::vector
            LIMIT :lim
        """
        params = {
            "status": ACTIVE_STATUS,
            "vec": vec_literal,
            "lim": limit,
        }
        if exclude_trade_name_id is not None:
            params["exclude_id"] = exclude_trade_name_id

        result = await self._session.execute(text(sql), params)
        rows = result.fetchall()
        return [
            IndexEntry(
                id=r[0],
                trade_name_id=r[1],
                normalized_ar=r[2],
                normalized_en=r[3],
                phonetic_key=r[4],
                category_id=r[5],
                status=r[6],
                similarity_score=float(r[7]),
            )
            for r in rows
        ]

    # -----------------------------------------------------------------------
    # Stage ⑦ — Upsert (F15 index sync)
    # -----------------------------------------------------------------------
    async def upsert(
        self,
        trade_name_id: int,
        normalized_ar: str,
        normalized_en: str,
        phonetic_key: str,
        status: str,
        category_id: Optional[int] = None,
        embedding_ar: Optional[list[float]] = None,
        embedding_en: Optional[list[float]] = None,
        expiry_date=None,
    ) -> None:
        """
        Insert or update a TradeNameIndex entry.
        Called by the sync worker after processing an outbox row.

        The operation is idempotent: running it twice for the same trade_name_id
        produces the same state.
        """
        from sqlalchemy import select
        emb_ar_val = (
            "[" + ",".join(str(v) for v in embedding_ar) + "]"
            if embedding_ar else None
        )
        emb_en_val = (
            "[" + ",".join(str(v) for v in embedding_en) + "]"
            if embedding_en else None
        )

        stmt = select(TradeNameIndex).where(TradeNameIndex.trade_name_id == trade_name_id)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.normalized_ar = normalized_ar
            existing.normalized_en = normalized_en
            existing.phonetic_key = phonetic_key
            existing.status = status
            existing.category_id = category_id
            existing.embedding_ar = emb_ar_val
            existing.embedding_en = emb_en_val
            if expiry_date:
                existing.expiry_date = expiry_date
        else:
            new_entry = TradeNameIndex(
                trade_name_id=trade_name_id,
                normalized_ar=normalized_ar,
                normalized_en=normalized_en,
                phonetic_key=phonetic_key,
                status=status,
                category_id=category_id,
                embedding_ar=emb_ar_val,
                embedding_en=emb_en_val,
                expiry_date=expiry_date,
            )
            self._session.add(new_entry)
        await self._session.flush()

    # -----------------------------------------------------------------------
    # Stage ⑦ — Delete (F15, F21)
    # -----------------------------------------------------------------------
    async def delete(self, trade_name_id: int) -> None:
        """
        Remove a trade name from the index.
        Called by the sync worker when a trade name is deleted from the master DB.
        F21: released/rejected names removed from index so they become available.
        """
        sql = "DELETE FROM trade_name_index WHERE trade_name_id = :tid"
        await self._session.execute(text(sql), {"tid": trade_name_id})

    async def set_status(self, trade_name_id: int, new_status: str) -> None:
        """
        Update the status of an index entry without rebuilding embeddings.
        Used when a name is released or expired (status change only).
        """
        sql = """
            UPDATE trade_name_index
            SET status = :status, updated_at = now()
            WHERE trade_name_id = :tid
        """
        await self._session.execute(text(sql), {"status": new_status, "tid": trade_name_id})
