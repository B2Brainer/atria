import os
import stat
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.persistence.adapter import PersistenceAdapter
from core.interaction.models import ExecutionMetrics, InteractionRequest, InteractionResult
from core.records.models import InteractionRecord
from sqlalchemy import create_engine, text
from sqlalchemy.exc import NoResultFound


def _request() -> InteractionRequest:
    return InteractionRequest(
        input="hello", provider_id="openai", model_id="gpt-x", parameters={"temperature": 0.2}
    )


def _result(cost: Decimal = Decimal("1.230")) -> InteractionResult:
    return InteractionResult(
        output="hi there",
        status="success",
        metrics=ExecutionMetrics(input_tokens=10, output_tokens=5, duration=0.5, cost=cost),
    )


def test_round_trip_with_result_and_metrics(adapter):
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request(), result=_result())
    adapter.save(record)

    retrieved = adapter.get(record.id)

    assert retrieved == record


def test_round_trip_without_result(adapter):
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request(), result=None)
    adapter.save(record)

    retrieved = adapter.get(record.id)

    assert retrieved.result is None
    assert retrieved == record


def test_round_trip_with_result_present_metrics_absent(adapter):
    result = InteractionResult(output="hi there", status="success", metrics=None)
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request(), result=result)
    adapter.save(record)

    retrieved = adapter.get(record.id)

    assert retrieved.result is not None
    assert retrieved.result.metrics is None


def test_list_by_cycle_filters_and_returns_empty_for_unknown_cycle(adapter):
    cycle_a, cycle_b = uuid4(), uuid4()
    record_a1 = InteractionRecord(cycle_id=cycle_a, sequence=1, request=_request())
    record_a2 = InteractionRecord(cycle_id=cycle_a, sequence=2, request=_request())
    record_b1 = InteractionRecord(cycle_id=cycle_b, sequence=1, request=_request())
    for record in (record_a1, record_a2, record_b1):
        adapter.save(record)

    records_a = adapter.list_by_cycle(cycle_a)

    assert {r.id for r in records_a} == {record_a1.id, record_a2.id}
    assert adapter.list_by_cycle(uuid4()) == []


def test_get_raises_for_unknown_record_id(adapter):
    with pytest.raises(NoResultFound):
        adapter.get(uuid4())


def test_save_twice_with_same_id_upserts_not_duplicates(adapter):
    cycle_id = uuid4()
    record = InteractionRecord(cycle_id=cycle_id, sequence=1, request=_request(), result=None)
    adapter.save(record)

    updated = record.model_copy(update={"result": _result()})
    adapter.save(updated)

    assert adapter.get(record.id).result is not None
    assert len(adapter.list_by_cycle(cycle_id)) == 1


def test_fresh_database_migration_establishes_applied_version(db_path):
    PersistenceAdapter(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0001"


def test_construction_against_fresh_database_requires_no_manual_migration(db_path):
    adapter = PersistenceAdapter(db_path)
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request())

    adapter.save(record)

    assert adapter.get(record.id) == record


def test_database_file_is_restricted_to_owner_permissions(db_path):
    PersistenceAdapter(db_path)

    mode = stat.S_IMODE(os.stat(db_path).st_mode)
    assert mode == 0o600


def test_in_memory_database_migrates_the_same_connection_the_adapter_uses():
    # Regression: migrations must run against PersistenceAdapter's own
    # connection, not a second engine built from a "sqlite:///:memory:" URL
    # string — two such engines would each open their own, unrelated
    # in-memory database, leaving save()/get() hitting an unmigrated one.
    adapter = PersistenceAdapter(":memory:")
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request())

    adapter.save(record)

    assert adapter.get(record.id) == record


def test_durability_across_adapter_recreation(db_path):
    first = PersistenceAdapter(db_path)
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request(), result=_result())
    first.save(record)
    del first

    second = PersistenceAdapter(db_path)
    assert second.get(record.id) == record


def test_decimal_cost_round_trips_without_precision_loss(adapter):
    cost = Decimal("12.345")
    record = InteractionRecord(
        cycle_id=uuid4(), sequence=1, request=_request(), result=_result(cost=cost)
    )
    adapter.save(record)

    retrieved = adapter.get(record.id)

    assert retrieved.result.metrics.cost == cost
    assert str(retrieved.result.metrics.cost) == str(cost)


def test_future_migration_is_discovered_and_applied_automatically_preserving_data(
    tmp_path, db_path
):
    migrations_root = tmp_path / "migrations"
    migrations_root.mkdir()
    versions_dir = migrations_root / "versions"
    versions_dir.mkdir()

    env_source = (
        (
            __import__("pathlib").Path(__file__).resolve().parents[3]
            / "adapters"
            / "persistence"
            / "migrations"
            / "env.py"
        )
        .read_text()
    )
    (migrations_root / "env.py").write_text(env_source)

    v1_source = (
        (
            __import__("pathlib").Path(__file__).resolve().parents[3]
            / "adapters"
            / "persistence"
            / "migrations"
            / "versions"
            / "0001_initial.py"
        )
        .read_text()
    )
    (versions_dir / "0001_initial.py").write_text(v1_source)

    first = PersistenceAdapter(db_path, migrations_dir=migrations_root)
    record = InteractionRecord(cycle_id=uuid4(), sequence=1, request=_request(), result=_result())
    first.save(record)
    del first

    (versions_dir / "0002_add_note_column.py").write_text(
        '''
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column("interaction_records", sa.Column("note", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("interaction_records", "note")
'''
    )

    second = PersistenceAdapter(db_path, migrations_dir=migrations_root)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0002"
    assert second.get(record.id) == record


def test_list_cycles_returns_distinct_cycles_ordered_by_most_recent_activity(adapter):
    cycle_a, cycle_b, cycle_c = uuid4(), uuid4(), uuid4()
    adapter.save(InteractionRecord(cycle_id=cycle_a, sequence=1, request=_request()))
    adapter.save(InteractionRecord(cycle_id=cycle_b, sequence=1, request=_request()))
    adapter.save(InteractionRecord(cycle_id=cycle_b, sequence=2, request=_request()))
    adapter.save(InteractionRecord(cycle_id=cycle_c, sequence=1, request=_request()))

    cycles = adapter.list_cycles()

    assert cycles == [cycle_c, cycle_b, cycle_a]


def test_list_cycles_returns_empty_list_for_empty_database(adapter):
    assert adapter.list_cycles() == []


def test_fresh_database_can_apply_a_second_migration_in_sequence(tmp_path):
    migrations_root = tmp_path / "migrations_seq"
    migrations_root.mkdir()
    versions_dir = migrations_root / "versions"
    versions_dir.mkdir()

    import pathlib

    base = pathlib.Path(__file__).resolve().parents[3] / "adapters" / "persistence" / "migrations"
    (migrations_root / "env.py").write_text((base / "env.py").read_text())
    v1_source = (base / "versions" / "0001_initial.py").read_text()
    (versions_dir / "0001_initial.py").write_text(v1_source)
    (versions_dir / "0002_add_note_column.py").write_text(
        '''
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column("interaction_records", sa.Column("note", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("interaction_records", "note")
'''
    )

    db_file = str(migrations_root.parent / "seq.sqlite3")
    PersistenceAdapter(db_file, migrations_dir=migrations_root)

    engine = create_engine(f"sqlite:///{db_file}")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0002"
