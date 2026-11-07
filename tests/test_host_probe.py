from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from queen_os.cli import main
from queen_os.hive import Hive
from queen_os.host.probe import SENSORS, probe
from queen_os.serial import canonicalize

STATUSES = {"OK", "UNAVAILABLE", "ERROR"}


def test_probe_reports_every_sensor_honestly_on_this_os() -> None:
    report = probe()
    assert set(report["sensors"]) == set(SENSORS)
    for name, sensor in report["sensors"].items():
        assert sensor["status"] in STATUSES, name
        assert ("value" in sensor) == (sensor["status"] == "OK"), name
        assert sensor["status"] == "OK" or sensor["reason"], name
    assert report["sensors"]["cpu"]["status"] == "OK"
    assert report["sensors"]["memory"]["status"] == "OK"
    canonicalize(report)  # must be ledger-safe on every OS


def test_absent_hardware_is_never_a_pass(tmp_path: Path) -> None:
    """Two-arm, for Pillar 1's own defect: with no PTP/TPM/NUMA present, nothing may read OK."""
    report = probe(root=tmp_path)
    for name in ("tpm", "ptp", "numa", "hugepages"):
        assert report["sensors"][name]["status"] != "OK", name
    assert report["clock_discipline"] == "system"


def test_synthetic_linux_tree_reads_raw_pcr_values(tmp_path: Path) -> None:
    if sys.platform != "linux":
        return  # the TPM sensor only reads sysfs on Linux
    pcr = tmp_path / "sys/class/tpm/tpm0/pcr-sha256"
    pcr.mkdir(parents=True)
    (tmp_path / "sys/class/tpm/tpm0/tpm_version_major").write_text("2\n")
    for i in range(15):
        (pcr / str(i)).write_text(f"{i:064X}\n")
    (tmp_path / "sys/class/ptp/ptp0").mkdir(parents=True)
    (tmp_path / "sys/class/ptp/ptp0/clock_name").write_text("igb_ptp\n")
    a = probe(root=tmp_path)
    assert a["sensors"]["tpm"]["status"] == "OK" and a["clock_discipline"] == "ptp"
    assert a["sensors"]["ptp"]["value"]["drift_ns"] is None  # presence is not a clock lock
    (pcr / "7").write_text("F" * 64)  # one PCR changes -> the attested digest changes
    b = probe(root=tmp_path)
    assert a["sensors"]["tpm"]["value"]["pcr_digest"] != b["sensors"]["tpm"]["value"]["pcr_digest"]
    (pcr / "3").chmod(0o000)
    import os

    if os.geteuid() != 0:  # root ignores permission bits
        assert probe(root=tmp_path)["sensors"]["tpm"]["status"] == "ERROR"


def test_probe_runs_standalone_with_stdlib_only() -> None:
    script = Path(__file__).resolve().parents[1] / "src" / "queen_os" / "host" / "probe.py"
    out = subprocess.run([sys.executable, "-I", "-S", str(script)], capture_output=True, text=True, check=True)
    assert set(json.loads(out.stdout)["sensors"]) == set(SENSORS)


def test_cli_records_signed_probe(tmp_path: Path) -> None:
    root = tmp_path / "hive"
    Hive.init(root, "probe").close()
    assert main(["host", "probe", "--hive", str(root)]) == 0
    with Hive.open(root) as hive:
        ev = hive.ledger.head()
        assert ev is not None and ev.kind == "host.probe" and ev.signer is not None
        assert hive.ledger.verify_chain(require_signatures=True) == 2
