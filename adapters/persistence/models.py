"""SQLAlchemy schema for persisted interaction records.

The composed ``InteractionRequest``/``InteractionResult``/``ExecutionMetrics``
sub-models are stored as a single JSON payload column (via Pydantic's own
``model_dump_json()``/``model_validate_json()``), rather than normalized into
separate columns/tables. Pydantic serializes ``Decimal`` fields as JSON
strings, so ``ExecutionMetrics.cost`` round-trips with no floating-point
precision loss. ``cycle_id`` and ``sequence`` are duplicated as queryable
columns so ``list_by_cycle()`` can filter without deserializing every row.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class InteractionRecordRow(Base):
    __tablename__ = "interaction_records"
    __table_args__ = (
        UniqueConstraint("cycle_id", "sequence", name="uq_interaction_records_cycle_sequence"),
    )

    id = Column(String, primary_key=True)
    cycle_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    payload = Column(String, nullable=False)
