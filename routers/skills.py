"""Skills CRUD + toggle."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services import skills

router = APIRouter(prefix="/api")


@router.get("/skills")
async def get_skills():
    return {"skills": await skills.list_skills()}


@router.post("/skills")
async def create_skill(request: Request):
    data = await request.json()
    if not (data.get("name") or "").strip():
        raise HTTPException(400, "Skill name required")
    return {"ok": True, "skill": await skills.create(data)}


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, request: Request):
    skill = await skills.update(skill_id, await request.json())
    if not skill:
        raise HTTPException(404, "Skill not found")
    return {"ok": True, "skill": skill}


@router.post("/skills/{skill_id}/toggle")
async def toggle_skill(skill_id: str):
    enabled = await skills.toggle(skill_id)
    if enabled is None:
        raise HTTPException(404, "Skill not found")
    return {"ok": True, "enabled": enabled}


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    if not await skills.delete(skill_id):
        raise HTTPException(404, "Skill not found")
    return {"ok": True}
