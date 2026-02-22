from codegraph.application.index_progress_tracker import IndexProgressTracker


def test_tracker_updates_counters_monotonically():
    t = IndexProgressTracker()
    op = t.start(mode="index", partitions_total=2, files_total=4)
    t.mark_file_done(op)
    t.mark_file_done(op)
    snap = t.get(op)
    assert snap.files_done == 2
