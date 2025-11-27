from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.db.base import get_session
from app.db.models import Taxonomy
from .schemas import (
    TaxonomyCreate,
    TaxonomyResponse,
    TaxonomyTreeResponse,
)
from app.core.security import require_role
from app.core.security import get_current_user_optional, get_current_user

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


@router.post("", response_model=TaxonomyResponse, status_code=201)
async def create_taxonomy(payload: TaxonomyCreate, current_user = Depends(require_role("admin")), db: AsyncSession = Depends(get_session)):
    node = Taxonomy(
        name=payload.name,
        description=payload.description,
        node_type=payload.node_type,
        parent_id=payload.parent_id,
        meta_data=payload.meta_data,
    )
    db.add(node)
    
    if payload.related_node_ids:
        result = await db.execute(select(Taxonomy).where(Taxonomy.id.in_(payload.related_node_ids)))
        node.related_nodes = result.scalars().all()

    await db.flush()

    # Set materialized path after id is available
    if node.parent_id:
        parent = await db.get(Taxonomy, node.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="parent_id not found")
        node.path = f"{parent.path}.{str(node.id)}" if parent.path else str(node.id)
    else:
        node.path = str(node.id)

    await db.commit()
    await db.refresh(node)
    return node


def build_tree(nodes: List[Taxonomy]) -> List[Dict]:
    by_id = {str(n.id): {**{"children": []}, **n.__dict__} for n in nodes}
    roots: List[Dict] = []

    # Create simple mapping and children lists
    for n in nodes:
        pid = str(n.parent_id) if n.parent_id else None
        nid = str(n.id)
        node_dict = {
            "id": nid,
            "name": n.name,
            "description": n.description,
            "node_type": n.node_type,
            "parent_id": str(n.parent_id) if n.parent_id else None,
            "path": n.path,
            "meta_data": n.meta_data,
            "created_at": n.created_at,
            "updated_at": n.updated_at,
            "children": [],
        }
        by_id[nid] = node_dict

    for nid, node in by_id.items():
        pid = node.get("parent_id")
        if pid and pid in by_id:
            by_id[pid]["children"].append(node)
        else:
            roots.append(node)

    return roots


@router.get("/tree", response_model=List[TaxonomyTreeResponse])
async def get_taxonomy_tree(db: AsyncSession = Depends(get_session), current_user = Depends(get_current_user)):
    result = await db.execute(select(Taxonomy).order_by(Taxonomy.name))
    nodes = result.scalars().all()
    tree = build_tree(nodes)
    return tree


@router.get("/{node_id}", response_model=TaxonomyResponse)
async def get_taxonomy_node(node_id: UUID, db: AsyncSession = Depends(get_session), current_user = Depends(get_current_user)):
    result = await db.execute(select(Taxonomy).options(selectinload(Taxonomy.related_nodes)).where(Taxonomy.id == node_id))
    node = result.scalars().first()
    if not node:
        raise HTTPException(status_code=404, detail="Taxonomy node not found")
    return node


@router.put("/{node_id}", response_model=TaxonomyResponse)
async def update_taxonomy_node(node_id: UUID, payload: TaxonomyCreate, current_user = Depends(require_role("admin")), db: AsyncSession = Depends(get_session)):
    node = await db.get(Taxonomy, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Taxonomy node not found")

    node.name = payload.name
    node.description = payload.description
    node.node_type = payload.node_type
    node.meta_data = payload.meta_data
    
    if payload.related_node_ids is not None:
        result = await db.execute(select(Taxonomy).where(Taxonomy.id.in_(payload.related_node_ids)))
        node.related_nodes = result.scalars().all()
        
    await db.commit()
    await db.refresh(node)
    return node


@router.put("/{node_id}/move", response_model=TaxonomyResponse)
async def move_taxonomy_node(node_id: UUID, parent_id: Optional[UUID], current_user = Depends(require_role("admin")), db: AsyncSession = Depends(get_session)):
    node = await db.get(Taxonomy, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Taxonomy node not found")

    if parent_id:
        parent = await db.get(Taxonomy, parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="New parent not found")
        node.parent_id = parent_id
        node.path = f"{parent.path}.{str(node.id)}" if parent.path else str(node.id)
    else:
        node.parent_id = None
        node.path = str(node.id)

    await db.commit()
    await db.refresh(node)
    return node


@router.delete("/{node_id}", status_code=204)
async def delete_taxonomy_node(node_id: UUID, current_user = Depends(require_role("admin")), db: AsyncSession = Depends(get_session)):
    node = await db.get(Taxonomy, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Taxonomy node not found")

    await db.delete(node)
    await db.commit()
    return None
