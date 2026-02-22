from codegraph.application.partition_planner import plan_partitions


def test_plan_groups_by_top_level_when_no_submodule():
    files = ["src/a.py", "src/b.py", "tests/t.py", "README.md"]
    parts = plan_partitions(files, submodules=[])
    roots = [p.root_path for p in parts]
    assert "src" in roots and "tests" in roots and "." in roots


def test_small_partitions_are_coalesced():
    files = ["a/x.py", "b/y.py", "c/z.py"]
    parts = plan_partitions(files, submodules=[], min_partition_files=2)
    assert len(parts) < 3
