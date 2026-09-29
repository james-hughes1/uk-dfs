"""Smoke test: the package imports and paths point inside the repo."""

import uk_dfs
from uk_dfs import config


def test_package_imports():
    assert uk_dfs.__version__


def test_data_dirs_are_inside_project():
    for path in (config.RAW_DIR, config.INTERIM_DIR, config.PROCESSED_DIR):
        assert config.PROJECT_ROOT in path.parents
