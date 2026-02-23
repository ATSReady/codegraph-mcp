from codegraph.application.index_progress_tracker import IndexProgressTracker


def test_tracker_updates_counters_monotonically():
    t = IndexProgressTracker()
    op = t.start(mode="index", partitions_total=2, files_total=4)
    t.mark_file_done(op)
    t.mark_file_done(op)
    snap = t.get(op)
    assert snap.files_done == 2


def test_tracker_tracks_partition_done_counts():
    t = IndexProgressTracker()
    op = t.start(mode="index", partitions_total=2, files_total=3)
    t.register_partitions(op, {"src": 2, "tests": 1})
    t.mark_file_done(op, partition="src")
    t.mark_file_failed(op, partition="src", error="x")
    t.mark_file_done(op, partition="tests")
    snap = t.get(op)
    assert snap is not None
    assert snap.partition_files_total["src"] == 2
    assert snap.partition_files_done["src"] == 2
    assert snap.partition_files_done["tests"] == 1
