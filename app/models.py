from __future__ import annotations

from datetime import datetime, date

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String, Integer, Float, Boolean,
    DateTime, ForeignKey, Date, Text,
    UniqueConstraint, func
)

class Base(DeclarativeBase):
    pass

class ApiTarget(Base):
    __tablename__ = "api_target"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    soap_action: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_type: Mapped[str] = mapped_column(String(50), nullable=False)  # validate/track/etc.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    probes: Mapped[list["ApiProbe"]] = relationship(back_populates="target")

class ApiProbe(Base):
    __tablename__ = "api_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("api_target.id"), nullable=False)

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    target: Mapped["ApiTarget"] = relationship(back_populates="probes")

class ApiDailyRollup(Base):
    __tablename__ = "api_daily_rollup"
    __table_args__ = (
        UniqueConstraint("target_id", "day", name="uq_rollup_target_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("api_target.id"), nullable=False)

    day: Mapped[date] = mapped_column(Date, nullable=False)

    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ok_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    avg_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    target: Mapped["ApiTarget"] = relationship()

class SiteNotice(Base):
    __tablename__ = "site_notice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # we'll use id=1
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notice_type: Mapped[str] = mapped_column(String(30), nullable=False, default="info")  # info|warning|maintenance
    message: Mapped[str] = mapped_column(Text, nullable=False, default="All systems operational.")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ApiNote(Base):
    __tablename__ = "api_note"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("api_target.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    target: Mapped["ApiTarget"] = relationship()


class IncidentUpdate(Base):
    __tablename__ = "incident_update"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # investigating|identified|monitoring|resolved|maintenance
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)