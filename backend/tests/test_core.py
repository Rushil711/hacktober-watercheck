import asyncio
import json
from datetime import UTC, datetime

import pytest

from app import config as C
from app.gemma import harness
from app.gemma.schemas import Verdicts
from app.models import Receipt
from app.providers import advisories, erddap
from app.scoring import chlorophyll_block, compute_halo

CHL_INFO = {
    "table": {
        "rows": [
            ["attribute", "NC_GLOBAL", "time_coverage_end", "String", "2026-10-23T12:00:00Z"],
            ["dimension", "latitude", "", "double", "nValues=4788, evenlySpaced=true, averageSpacing=-0.0375"],
            ["dimension", "longitude", "", "double", "nValues=9602, evenlySpaced=true, averageSpacing=0.0375"],
            ["variable", "chlor_a", "", "float", "time, altitude, latitude, longitude"],
            ["attribute", "chlor_a", "units", "String", "mg m^-3"],
        ]
    }
}

CHL_GRID = {
    "table": {
        "columnNames": ["time", "altitude", "latitude", "longitude", "chlor_a"],
        "rows": [
            ["2026-10-16T12:00:00Z", 0.0, 32.8687, -117.2813, 0.7],
            ["2026-10-16T12:00:00Z", 0.0, 32.8687, -117.2438, 1.2],
            ["2026-10-16T12:00:00Z", 0.0, 33.5, -118.0, 9.0],
            ["2026-10-23T12:00:00Z", 0.0, 32.8687, -117.2813, None],
        ],
    }
}


def test_metadata_parsing_reads_order_and_rejects_wrong_variable():
    meta = erddap.parse_metadata(C.CHL_DATASET, CHL_INFO)
    assert meta.lat_descending is True
    assert meta.lat_res == pytest.approx(0.0375)
    bad = C.GridDataset("x", "chl_oci", "mg m^-3", True, "t")
    with pytest.raises(erddap.MetadataError):
        erddap.parse_metadata(bad, CHL_INFO)


def test_grid_parsing_box_and_daily_mean():
    rows = erddap.parse_grid_json(C.CHL_DATASET, CHL_GRID)
    meta = erddap.parse_metadata(C.CHL_DATASET, CHL_INFO)
    grid = erddap.Grid(C.CHL_DATASET, meta, [erddap.Cell(*r) for r in rows], "u", "f", False)
    cells = erddap.cells_in_box(grid, 32.85585, -117.25897, C.OFFSHORE_BOX_KM)
    assert len(cells) == 3  # the far-away cell is excluded
    days = erddap.daily_means(cells)
    assert days[0].mean == pytest.approx(0.95)
    assert days[-1].mean is None  # cloudy day stays missing, never zero-filled


def test_stale_chlorophyll_is_flagged_and_turns_halo_amber():
    days = [erddap.DailyValue("2026-10-16", "2026-10-16T12:00:00Z", 1.1, 3, 4)]
    now = datetime(2026, 10, 25, 22, 0, tzinfo=UTC)
    block = chlorophyll_block(days, Receipt(source="test"), "2026-10-23T12:00:00Z", now)
    assert block.stale and block.age_days == pytest.approx(9.4)
    assert block.current.receipt.observed_at == "2026-10-16T12:00:00Z"
    halo = compute_halo("no_advisory_found", block.level, block.stale, True)
    assert halo.color == "amber" and "Chlorophyll data is old" in halo.reasons


def test_missing_chlorophyll_shows_unavailable():
    block = chlorophyll_block([], Receipt(source="test"), "2026-10-23T12:00:00Z")
    assert block.current.value is None and block.current.display == "Unavailable"


def test_no_advisory_found_is_not_safe_and_unmatched_is_unverified():
    site = {"id": "1", "name": "Test Beach", "lat": 0, "lon": 0}
    status, detail = advisories.status_from_county(site, 0.2, [], [])
    assert status == "no_advisory_found"
    assert "not the same as confirmed safe" in detail
    assert advisories.STATUS_LABELS[status] == "No advisory found"
    status, _ = advisories.status_from_county(site, 5.0, [], [])
    assert status == "unverified"
    assert compute_halo("advisory", "typical", False, True).color == "coral"


def test_old_beachwatch_records_are_unverified_not_active():
    latest = {
        "county_latest": "2026-03-03",
        "records": [{"AdvisoryType": "Posting", "DateofAdvisory": "2026-01-28", "DateOpened": None}],
    }
    status, detail = advisories.status_from_beachwatch(latest, datetime(2026, 10, 25, tzinfo=UTC))
    assert status == "unverified"
    assert "2026-03-03" in detail


def _fake(replies):
    calls = []

    async def generate(system, messages):
        calls.append(messages)
        return replies[len(calls) - 1]

    return generate, calls


GOOD = {
    "swim_feel": {"level": "mild", "verdict": "Mild water", "reason": "Sea temperature is about 66 °F from satellite."},
    "jump_feel": {
        "level": "mild",
        "verdict": "Mild, mid tide",
        "reason": "Tide is 3.2 ft. Depth, rocks, and surge need a local check.",
    },
}
PAYLOAD = {"sea_temp_f": 66.4, "swim_level": "mild", "jump_level": "mild", "tide_now_ft": 3.2}


def test_bad_gemma_json_retries_once_then_succeeds():
    gen, calls = _fake(["not json at all", json.dumps(GOOD)])
    out = asyncio.run(harness.run_skill("water_feel", PAYLOAD, Verdicts, generate=gen, use_cache=False))
    assert out.ok and out.attempts == 2 and len(calls) == 2
    assert "rejected" in calls[1][-1]["text"]


def test_bad_gemma_json_twice_hides_card():
    gen, _ = _fake(["{oops", "still bad"])
    out = asyncio.run(harness.run_skill("water_feel", PAYLOAD, Verdicts, generate=gen, use_cache=False))
    assert not out.ok and out.data is None and "failed validation twice" in out.error


def test_invented_number_is_rejected():
    invented = json.loads(json.dumps(GOOD))
    invented["swim_feel"]["reason"] = "Sea temperature is about 71 °F."
    gen, _ = _fake([json.dumps(invented), json.dumps(invented)])
    out = asyncio.run(harness.run_skill("water_feel", PAYLOAD, Verdicts, generate=gen, use_cache=False))
    assert not out.ok and "71" in out.error


def test_safe_claims_flagged_but_negations_and_safety_allowed():
    assert harness.unsafe_claims(["The water is safe to swim."])
    assert not harness.unsafe_claims(["No advisory found is not the same as confirmed safe."])
    assert not harness.unsafe_claims(["Jump safety: water feel only."])


def test_unicode_labels_keep_numbers_grounded():
    allowed = harness.allowed_numbers(json.dumps({"label": "4 PM–6 PM"}, ensure_ascii=False))
    assert harness.ungrounded_numbers(["Best from 4 PM to 6 PM"], allowed) == []
