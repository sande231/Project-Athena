"""Database tables (SQLAlchemy). Works with PostgreSQL in Kubernetes and SQLite for local tests."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[str] = mapped_column(String(64), default="demo-store")
    external_order_id: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[float | None] = mapped_column(Float)
    features: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    prediction: Mapped["Prediction"] = relationship(back_populates="transaction", uselist=False)
    label: Mapped["Label"] = relationship(back_populates="transaction", uselist=False)


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), unique=True)
    model_version: Mapped[str] = mapped_column(String(128))
    score: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(16), index=True)  # approve / review / block
    reason: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float] = mapped_column(Float)
    transaction: Mapped[Transaction] = relationship(back_populates="prediction")


class Label(Base):
    __tablename__ = "labels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), unique=True)
    is_fraud: Mapped[bool] = mapped_column(Boolean)
    labeled_by: Mapped[str] = mapped_column(String(64), default="analyst")
    labeled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    transaction: Mapped[Transaction] = relationship(back_populates="label")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32))          # drift / quality / system
    severity: Mapped[str] = mapped_column(String(16))      # info / warning / critical
    metric_snapshot: Mapped[dict] = mapped_column(JSON)
    ai_explanation: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
