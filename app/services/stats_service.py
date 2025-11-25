from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from uuid import UUID
import uuid

from app.db.models import (
    UserTaxonomyStats,
    QuestionTaxonomy,
    Taxonomy,
    Question,
    QuestionAttempt
)

async def update_user_taxonomy_stats(
    db: AsyncSession,
    user_id: UUID,
    question_id: UUID,
    score: Decimal,
    max_score: Decimal
):
    """
    Update UserTaxonomyStats for a given user and question attempt.
    Walks up the taxonomy tree and updates stats for all ancestors.
    """
    if not user_id:
        return

    # Gather taxonomy nodes for this question
    stmt = select(QuestionTaxonomy).where(QuestionTaxonomy.question_id == question_id)
    qlinks = (await db.execute(stmt)).scalars().all()
    taxonomy_ids = [ql.taxonomy_id for ql in qlinks]

    # For each taxonomy node, walk up parents and upsert stats
    for tid in taxonomy_ids:
        node = await db.get(Taxonomy, tid)
        ancestors = []
        cur = node
        while cur:
            ancestors.append(cur)
            if cur.parent_id:
                cur = await db.get(Taxonomy, cur.parent_id)
            else:
                break

        for anc in ancestors:
            # Coerce to UUID objects
            try:
                user_key = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
            except Exception:
                user_key = user_id

            try:
                tax_key = anc.id if isinstance(anc.id, uuid.UUID) else uuid.UUID(str(anc.id))
            except Exception:
                tax_key = anc.id

            # Try to fetch existing stats
            stmt = select(UserTaxonomyStats).where(
                UserTaxonomyStats.user_id == user_key, 
                UserTaxonomyStats.taxonomy_id == tax_key
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            
            if existing:
                existing.questions_attempted = (existing.questions_attempted or 0) + 1
                
                existing_total = Decimal(str(existing.total_score or 0))
                existing_max = Decimal(str(existing.max_possible_score or 0))
                
                new_total = existing_total + score
                new_max = existing_max + max_score
                
                existing.total_score = float(new_total)
                existing.max_possible_score = float(new_max)
                
                if score == max_score and max_score > 0:
                    existing.questions_correct = (existing.questions_correct or 0) + 1
                
                # Recompute average
                try:
                    if new_max > 0:
                        existing.average_score_percent = (float(new_total) / float(new_max) * 100)
                    else:
                        existing.average_score_percent = 0
                except Exception:
                    existing.average_score_percent = 0
            else:
                uts = UserTaxonomyStats(
                    user_id=user_key,
                    taxonomy_id=tax_key,
                    questions_attempted=1,
                    questions_correct=1 if (score == max_score and max_score > 0) else 0,
                    total_score=float(score),
                    max_possible_score=float(max_score),
                    average_score_percent=(float(score) / float(max_score) * 100) if max_score and max_score > 0 else 0,
                    meta_data={},
                )
                db.add(uts)
