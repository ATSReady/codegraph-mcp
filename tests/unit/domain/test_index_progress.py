from codegraph.domain.index_progress import IndexProgressSnapshot, ProgressState


def test_snapshot_defaults_are_stable():
    s = IndexProgressSnapshot(operation_id="op-1", mode="index")
    assert s.state == ProgressState.QUEUED
    assert s.files_done == 0
    assert s.partitions_total == 0
