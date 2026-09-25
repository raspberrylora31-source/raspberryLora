"""Mesh node list and details."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.node_service import get_node, list_nodes, node_to_dict

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
def api_list_nodes(q: str | None = Query(default=None, max_length=64), db: Session = Depends(get_db)) -> dict:
    rows = [node_to_dict(n) for n in list_nodes(db, q)]
    return {"nodes": rows, "count": len(rows)}


@router.get("/{node_id}")
def api_get_node(node_id: str, db: Session = Depends(get_db)) -> dict:
    node = get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node_to_dict(node)
