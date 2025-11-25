from typing import List, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.base import get_session
from app.db.models import Taxonomy, UserTaxonomyStats
from app.core.security import get_current_user
from app.api.v1.schemas import TaxonomyTreeResponse

router = APIRouter(prefix="/stats", tags=["stats"])


def build_annotated_tree(nodes: List[Taxonomy], stats_map: Dict[str, dict]) -> List[TaxonomyTreeResponse]:
    """Build tree using Pydantic models for proper serialization"""
    by_id = {}
    for n in nodes:
        nid = str(n.id)
        stat = stats_map.get(nid, {})
        
        # Create Pydantic model instance
        by_id[nid] = TaxonomyTreeResponse(
            id=nid,
            name=n.name,
            description=n.description,
            node_type=n.node_type,
            parent_id=str(n.parent_id) if n.parent_id else None,
            path=n.path,
            meta_data=n.meta_data or {},
            created_at=n.created_at,
            updated_at=n.updated_at,
            children=[],
            questions_attempted=int(stat.get("questions_attempted", 0)),
            questions_correct=int(stat.get("questions_correct", 0)),
            average_score_percent=float(stat.get("average_score_percent", 0)),
        )

    # Build tree structure
    roots = []
    for nid, node in by_id.items():
        pid = node.parent_id
        if pid and pid in by_id:
            by_id[pid].children.append(node)
        else:
            roots.append(node)

    return roots


@router.get("/me/taxonomy/tree", response_model=List[TaxonomyTreeResponse])
async def get_my_taxonomy_tree(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_session)):
    # Fetch all taxonomy nodes
    res = await db.execute(select(Taxonomy).order_by(Taxonomy.name))
    nodes = res.scalars().all()

    # Fetch stats for this user
    res2 = await db.execute(select(UserTaxonomyStats).where(UserTaxonomyStats.user_id == current_user.id))
    stats = res2.scalars().all()
    stats_map = {
        str(s.taxonomy_id): {
            "questions_attempted": s.questions_attempted,
            "questions_correct": s.questions_correct,
            "average_score_percent": float(s.average_score_percent or 0)
        } for s in stats
    }

    tree = build_annotated_tree(nodes, stats_map)
    return tree
