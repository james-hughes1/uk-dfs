"""NESO fetchers: skip files already on disk, never leave a half-written file behind."""

import pandas as pd
import pytest

from uk_dfs.data import neso


@pytest.fixture
def fake_urlopen(monkeypatch):
    calls = []

    class Response:
        def __init__(self, url):
            calls.append(url)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"a,b\n1,2\n"

    monkeypatch.setattr(neso.urllib.request, "urlopen", lambda url, timeout: Response(url))
    return calls


def test_downloads_missing_and_skips_existing(tmp_path, fake_urlopen):
    out = tmp_path / "x.csv"
    assert neso._download("https://example/x.csv", out, force=False) is True
    assert out.read_text() == "a,b\n1,2\n"
    assert neso._download("https://example/x.csv", out, force=False) is False
    assert len(fake_urlopen) == 1
    assert neso._download("https://example/x.csv", out, force=True) is True


def test_empty_file_is_refetched(tmp_path, fake_urlopen):
    out = tmp_path / "x.csv"
    out.write_text("")
    assert neso._download("https://example/x.csv", out, force=False) is True


def test_failed_download_leaves_no_file(tmp_path, monkeypatch):
    def boom(url, timeout):
        raise OSError("network down")

    monkeypatch.setattr(neso.urllib.request, "urlopen", boom)
    out = tmp_path / "x.csv"
    with pytest.raises(OSError):
        neso._download("https://example/x.csv", out, force=False)
    assert not out.exists()


def test_urls_point_at_the_neso_api():
    for dataset, resource, remote in neso.DFS_FILES.values():
        assert neso._url(dataset, resource, remote).startswith("https://api.neso.energy/dataset/")


def test_read_dfs_tidies_2022_23_files(tmp_path):
    """2022/23 headers carry trailing spaces, dates are day-first, no direction column."""
    path = tmp_path / "2223_live_summary.csv"
    path.write_text(
        "Date,From,To,DFS Required,DFS Procured ,Settled Volume\n"
        "24/01/2023,16:30,17:00,274,288.62,233.12\n"
    )
    df = neso.read_dfs(path, "2022/23", "Live")
    row = df.iloc[0]
    assert row.start == pd.Timestamp("2023-01-24 16:30")
    assert row.proc == 288.62
    assert row.settled == 233.12
    assert row.direction == "Downwards"
    assert row.type == "Live"
