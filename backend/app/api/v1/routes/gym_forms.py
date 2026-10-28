"""Tenant-scoped admin workflows for waivers and signed health forms."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer, undefer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_client_ip, get_session, require_capability, require_writable_org
from app.core.permissions import Capability
from app.core.security import now_utc
from app.core.tenancy import TenantContext
from app.models.gym_form import GymForm, GymFormAcceptance
from app.models.membership import OrganizationMember
from app.schemas.gym_forms import (
    GymFormAcceptanceOut, GymFormCreate, GymFormOption, GymFormOut,
)
from app.services.audit_service import record_audit

router = APIRouter()
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
ALLOWED_EVIDENCE = {
    b"%PDF-": "application/pdf",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"RIFF": "image/webp",
}


def _response(row: GymForm) -> GymFormOut:
    return GymFormOut.model_validate(row)


@router.get("/forms", response_model=list[GymFormOut])
async def list_forms(
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(select(GymForm).where(
        GymForm.organization_id == ctx.org_id,
    ).order_by(GymForm.form_key, GymForm.version.desc()))).scalars().all()
    return [_response(row) for row in rows]


@router.post("/forms", response_model=GymFormOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def create_form(
    data: GymFormCreate,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    row = GymForm(
        organization_id=ctx.org_id, form_key=uuid.uuid4().hex,
        title=data.title, form_type=data.form_type, body=data.body, created_by=ctx.user_id,
    )
    session.add(row)
    await session.flush()
    await record_audit(
        session, action="gym_form.created", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="gym_form", entity_id=row.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"form_type": row.form_type, "version": row.version},
    )
    return _response(row)


@router.post("/forms/{form_id}/versions", response_model=GymFormOut, status_code=201,
             dependencies=[Depends(require_writable_org)])
async def create_form_version(
    form_id: str,
    data: GymFormCreate,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    previous = (await session.execute(select(GymForm).where(
        GymForm.id == form_id, GymForm.organization_id == ctx.org_id,
    ).with_for_update())).scalar_one_or_none()
    if previous is None or not previous.active:
        raise HTTPException(status_code=404, detail="Active form not found.")
    latest_version = (await session.execute(select(GymForm.version).where(
        GymForm.organization_id == ctx.org_id, GymForm.form_key == previous.form_key,
    ).order_by(GymForm.version.desc()).limit(1))).scalar_one()
    previous.active = False
    row = GymForm(
        organization_id=ctx.org_id, form_key=previous.form_key,
        title=data.title, form_type=data.form_type, body=data.body,
        version=latest_version + 1, created_by=ctx.user_id,
    )
    session.add(row)
    await session.flush()
    await record_audit(
        session, action="gym_form.version_created", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="gym_form", entity_id=row.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"form_type": row.form_type, "version": row.version},
    )
    return _response(row)


@router.post("/forms/{form_id}/archive", response_model=GymFormOut,
             dependencies=[Depends(require_writable_org)])
async def archive_form(
    form_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_session),
):
    row = (await session.execute(select(GymForm).where(
        GymForm.id == form_id, GymForm.organization_id == ctx.org_id, GymForm.active.is_(True),
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Active form not found.")
    row.active = False
    await record_audit(
        session, action="gym_form.archived", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="gym_form", entity_id=row.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"version": row.version},
    )
    return _response(row)


@router.get("/collection-forms", response_model=list[GymFormOption])
async def collection_forms(
    ctx: TenantContext = Depends(require_capability(Capability.COLLECT_MEMBER_FORMS)),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(select(GymForm).where(
        GymForm.organization_id == ctx.org_id, GymForm.active.is_(True),
    ).order_by(GymForm.title))).scalars().all()
    return [GymFormOption(id=row.id, title=row.title, form_type=row.form_type, version=row.version)
            for row in rows]


@router.post("/members/{member_id}/acceptances", response_model=GymFormAcceptanceOut,
             status_code=201, dependencies=[Depends(require_writable_org)])
async def record_acceptance(
    member_id: str,
    request: Request,
    form_id: str = Form(),
    signed_by_name: str = Form(min_length=2, max_length=160),
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(require_capability(Capability.COLLECT_MEMBER_FORMS)),
    session: AsyncSession = Depends(get_session),
):
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.id == member_id, OrganizationMember.organization_id == ctx.org_id,
        OrganizationMember.banned.is_(False),
    ).with_for_update())).scalar_one_or_none()
    form = (await session.execute(select(GymForm).where(
        GymForm.id == form_id, GymForm.organization_id == ctx.org_id, GymForm.active.is_(True),
    ).with_for_update())).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if form is None:
        raise HTTPException(status_code=404, detail="Active form not found.")
    signed_name = signed_by_name.strip()
    if len(signed_name) < 2:
        raise HTTPException(status_code=422, detail="Enter the name shown on the signed document.")
    already_signed = (await session.execute(select(GymFormAcceptance.id).where(
        GymFormAcceptance.organization_id == ctx.org_id,
        GymFormAcceptance.member_id == member.id,
        GymFormAcceptance.form_id == form.id,
    ))).scalar_one_or_none()
    if already_signed:
        raise HTTPException(status_code=409, detail="This member already has a signed copy of this form version.")
    data = await file.read(MAX_EVIDENCE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="Attach the signed form evidence.")
    if len(data) > MAX_EVIDENCE_BYTES:
        raise HTTPException(status_code=413, detail="Signed evidence must be 10MB or smaller.")
    media_type = next((kind for magic, kind in ALLOWED_EVIDENCE.items() if data.startswith(magic)), None)
    if media_type == "image/webp" and data[8:12] != b"WEBP":
        media_type = None
    if media_type is None:
        raise HTTPException(status_code=422, detail="Upload a valid PDF, PNG, JPEG, or WebP signed document.")
    filename = Path(file.filename or "signed-form").name.replace("\x00", "")[:180]
    row = GymFormAcceptance(
        organization_id=ctx.org_id, member_id=member.id, form_id=form.id,
        form_title=form.title, form_type=form.form_type, form_version=form.version,
        form_body_snapshot=form.body, signed_by_name=signed_name,
        collected_by=ctx.user_id, evidence_data=data, evidence_media_type=media_type,
        evidence_filename=filename, evidence_sha256=hashlib.sha256(data).hexdigest(),
        recorded_at=now_utc(),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="This member already has a signed copy of this form version.") from exc
    await record_audit(
        session, action="gym_form.acceptance_recorded", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="gym_form_acceptance", entity_id=row.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"member_id": member.id, "form_id": form.id, "version": form.version,
                  "evidence_sha256": row.evidence_sha256},
    )
    return GymFormAcceptanceOut(
        id=row.id, member_id=row.member_id, form_title=row.form_title, form_type=row.form_type,
        form_version=row.form_version, signed_by_name=row.signed_by_name, recorded_at=row.recorded_at,
        collected_by=row.collected_by, evidence_filename=row.evidence_filename,
        evidence_media_type=row.evidence_media_type, evidence_sha256=row.evidence_sha256,
    )


@router.get("/members/{member_id}/acceptances", response_model=list[GymFormAcceptanceOut])
async def member_acceptances(
    member_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PRIVATE_MEMBER_PROFILE)),
    session: AsyncSession = Depends(get_session),
):
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.id == member_id, OrganizationMember.organization_id == ctx.org_id,
    ))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    rows = (await session.execute(select(GymFormAcceptance).where(
        GymFormAcceptance.organization_id == ctx.org_id,
        GymFormAcceptance.member_id == member.id,
    ).options(defer(GymFormAcceptance.evidence_data)).order_by(
        GymFormAcceptance.recorded_at.desc()))).scalars().all()
    await record_audit(
        session, action="gym_form.acceptances_viewed", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="member", entity_id=member.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"count": len(rows)},
    )
    return [GymFormAcceptanceOut(
        id=row.id, member_id=row.member_id, form_title=row.form_title, form_type=row.form_type,
        form_version=row.form_version, signed_by_name=row.signed_by_name, recorded_at=row.recorded_at,
        collected_by=row.collected_by, evidence_filename=row.evidence_filename,
        evidence_media_type=row.evidence_media_type, evidence_sha256=row.evidence_sha256,
    ) for row in rows]


@router.get("/acceptances/{acceptance_id}/evidence")
async def acceptance_evidence(
    acceptance_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_capability(Capability.VIEW_PRIVATE_MEMBER_PROFILE)),
    session: AsyncSession = Depends(get_session),
):
    row = (await session.execute(select(GymFormAcceptance).options(
        undefer(GymFormAcceptance.evidence_data),
    ).where(
        GymFormAcceptance.id == acceptance_id,
        GymFormAcceptance.organization_id == ctx.org_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Signed evidence not found.")
    await record_audit(
        session, action="gym_form.evidence_viewed", organization_id=ctx.org_id,
        actor_user_id=ctx.user_id, entity_type="gym_form_acceptance", entity_id=row.id,
        ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"),
        metadata={"member_id": row.member_id, "evidence_sha256": row.evidence_sha256},
    )
    extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg",
                 "image/webp": "webp"}[row.evidence_media_type]
    return Response(row.evidence_data, media_type=row.evidence_media_type, headers={
        "Content-Disposition": f'attachment; filename="signed-form-{row.id}.{extension}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })
