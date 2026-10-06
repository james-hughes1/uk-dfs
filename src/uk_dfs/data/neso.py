"""NESO Data Portal downloads: DFS event data and historic national demand.

Everything comes from the public NESO API (https://api.neso.energy, no key needed). Each
DFS season is published as its own dataset with three CSVs:

- requirement   what NESO asked for: MW needed per half-hour
- utilisation   one row per accepted bid: provider, unit, MW, price, regional split
- summary       one row per event half-hour: required, procured, cost, settled volume

2022/23 published live and test events as separate datasets. Files are saved under short
names (e.g. `2223_live_summary.csv`) because NESO's own names change between releases.

Fetches are idempotent: a file already on disk is left alone unless `force=True`.
"""

import urllib.request
from pathlib import Path

from uk_dfs.config import RAW_DIR

API = "https://api.neso.energy/dataset"
DFS_DIR = RAW_DIR / "neso_dfs"
DEMAND_DIR = RAW_DIR / "neso_demand"

# local file name -> (dataset id, resource id, NESO file name)
DFS_FILES = {
    "2223_live_requirement.csv": (
        "328b830b-4a8e-4dce-a14b-be91ed926b95", "663f3f82-fec8-4c9a-a837-df5db8690a6f",
        "dfs-service-requirement-live230120231430.csv"),
    "2223_live_utilisation.csv": (
        "328b830b-4a8e-4dce-a14b-be91ed926b95", "4e87244e-2479-4e6e-84c2-698dffaca41f",
        "dfs-participant-utilisation-report-live2501231600.csv"),
    "2223_live_summary.csv": (
        "328b830b-4a8e-4dce-a14b-be91ed926b95", "011f1a15-f63f-4a95-b1eb-453e5ffcd176",
        "utilisation-report-summary-live2501231600-fs.csv"),
    "2223_test_utilisation.csv": (
        "22bc9bdd-4919-439a-95b8-5213bb3bdf4c", "fc466b76-6823-4dd9-8b4a-aab464e0e77b",
        "dfs-participant-utilisation-report-test280320231300.csv"),
    "2223_test_summary.csv": (
        "22bc9bdd-4919-439a-95b8-5213bb3bdf4c", "e4804faf-92be-43d0-a1ec-3e52a50f9666",
        "utilisation-report-summary-test280320231300-fs.csv"),
    "2325_requirement.csv": (
        "e5277fca-2a2b-4836-933b-f24a676b9ed8", "7914dd99-fe1c-41ba-9989-5784531c58bb",
        "dfs-service-requirements.csv"),
    "2325_utilisation.csv": (
        "e5277fca-2a2b-4836-933b-f24a676b9ed8", "ed7019b0-32b7-425c-a2fb-5ba9e32733fb",
        "dfs-utilisation-report.csv"),
    "2325_summary.csv": (
        "e5277fca-2a2b-4836-933b-f24a676b9ed8", "71a9cb04-8935-4e3a-bdd6-17f6fff0a7c6",
        "dfs-utilisation-report-summary.csv"),
    "2526_requirement.csv": (
        "829e325f-8926-40ab-9dd6-8b7aea6cb244", "f5605e2b-b677-424c-8df7-d0ce4ee03cef",
        "dfs-service-requirement.csv"),
    "2526_utilisation.csv": (
        "829e325f-8926-40ab-9dd6-8b7aea6cb244", "cc36fff5-5f6f-4fde-8932-c935d982ecd8",
        "dfs-utilisation-report.csv"),
    "2526_summary.csv": (
        "829e325f-8926-40ab-9dd6-8b7aea6cb244", "25698259-0b66-42f0-ac59-ef0df5245812",
        "dfs-utilisation-report-summary.csv"),
    "2627_requirement.csv": (
        "829e325f-8926-40ab-9dd6-8b7aea6cb244", "3635fd80-49d7-4d02-964d-cc8c08d50302",
        "dfs-service-requirement.csv"),
    "2627_utilisation.csv": (
        "829e325f-8926-40ab-9dd6-8b7aea6cb244", "3ebf77d7-05df-466e-a023-dc45a90efeea",
        "dfs-utilisation-report.csv"),
    "2627_summary.csv": (
        "829e325f-8926-40ab-9dd6-8b7aea6cb244", "705e573c-ddac-4675-b410-82916b35c4fe",
        "dfs-utilisation-report-summary.csv"),
}  # fmt: skip

# Historic demand data: one CSV per calendar year (the current year is "demanddataupdate")
DEMAND_DATASET = "8f2fe0af-871c-488d-8bad-960426f24601"
DEMAND_FILES = {
    "demand_2022.csv": ("bb44a1b5-75b1-4db2-8491-257f23385006", "demanddata_2022.csv"),
    "demand_2023.csv": ("bf5ab335-9b40-4ea4-b93a-ab4af7bce003", "demanddata_2023.csv"),
    "demand_2024.csv": ("f6d02c0f-957b-48cb-82ee-09003f2ba759", "demanddata_2024.csv"),
    "demand_2025.csv": ("b2bde559-3455-4021-b179-dfe60c0337b0", "demanddata_2025.csv"),
    "demand_2026.csv": ("8a4a771c-3929-4e56-93ad-cdf13219dea5", "demanddataupdate_2026.csv"),
}


def _url(dataset: str, resource: str, name: str) -> str:
    return f"{API}/{dataset}/resource/{resource}/download/{name}"


def _download(url: str, out: Path, force: bool) -> bool:
    """Download `url` to `out` unless it's already there. Returns True if it downloaded."""
    if out.exists() and out.stat().st_size > 0 and not force:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")  # so a failed download never looks complete
    with urllib.request.urlopen(url, timeout=120) as r:
        tmp.write_bytes(r.read())
    tmp.replace(out)
    return True


def fetch_dfs(force: bool = False) -> list[str]:
    """Cache every DFS season's CSVs in data/raw/neso_dfs/. Returns the files downloaded."""
    return [
        name
        for name, (dataset, resource, remote) in DFS_FILES.items()
        if _download(_url(dataset, resource, remote), DFS_DIR / name, force)
    ]


def fetch_demand(force: bool = False) -> list[str]:
    """Cache historic national demand in data/raw/neso_demand/. Returns the files downloaded.

    The current year's file grows through the year; pass `force=True` to refresh it.
    """
    return [
        name
        for name, (resource, remote) in DEMAND_FILES.items()
        if _download(_url(DEMAND_DATASET, resource, remote), DEMAND_DIR / name, force)
    ]
