"""Zero-dependency host probe (Pillar 1 `seed_capsule.py`, corrected; see BUILD_MAP v0.2).

Standard library only, so it runs before dependencies are installed:
``python src/queen_os/host/probe.py``.

Every sensor reports exactly one of:
    OK           measured on this machine; ``value`` holds the measurement
    UNAVAILABLE  the hardware or interface is absent; ``reason`` says which
    ERROR        the interface exists but reading it failed; ``reason`` says how
A missing sensor is never reported as a pass. That is the Non-Simulation Contract,
and the defect this module corrects in Pillar 1's PTP check.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess  # noqa: S404 - fixed argv, no shell, used only for read-only vendor tools
import sys
from pathlib import Path
from typing import Any

Sensor = dict[str, Any]


def ok(value: Any) -> Sensor:
    return {"status": "OK", "value": value}


def unavailable(reason: str) -> Sensor:
    return {"status": "UNAVAILABLE", "reason": reason}


def error(reason: str) -> Sensor:
    return {"status": "ERROR", "reason": reason}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _run(argv: list[str], timeout: float = 5.0) -> str | None:
    if shutil.which(argv[0]) is None:
        return None
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=True)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


# -- individual sensors ---------------------------------------------------------------


def cpu(root: Path) -> Sensor:
    info: dict[str, Any] = {"logical_cpus": os.cpu_count(), "machine": platform.machine()}
    cpuinfo = root / "proc" / "cpuinfo"
    if cpuinfo.exists():
        text = _read(cpuinfo)
        model = re.search(r"^(model name|Model|Hardware)\s*:\s*(.+)$", text, re.M)
        parts = sorted(set(re.findall(r"^CPU part\s*:\s*(\S+)$", text, re.M)))
        implementer = sorted(set(re.findall(r"^CPU implementer\s*:\s*(\S+)$", text, re.M)))
        if model:
            info["model"] = model.group(2).strip()
        if parts:  # ARM: Ampere Altra (Neoverse N1) reports implementer 0x41, part 0xd0c
            info["arm_cpu_part"] = parts
            info["arm_implementer"] = implementer
    elif sys.platform == "darwin":
        brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if brand:
            info["model"] = brand
    else:
        info["model"] = platform.processor() or None
    return ok(info)


def memory(root: Path) -> Sensor:
    meminfo = root / "proc" / "meminfo"
    if meminfo.exists():
        m = re.search(r"^MemTotal:\s+(\d+) kB", _read(meminfo), re.M)
        return ok({"total_bytes": int(m.group(1)) * 1024}) if m else error("MemTotal missing from /proc/meminfo")
    if sys.platform == "darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        return ok({"total_bytes": int(out)}) if out and out.isdigit() else error("sysctl hw.memsize failed")
    if sys.platform == "win32":
        import ctypes

        class MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                (n, ctypes.c_ulonglong)
                for n in ("total", "avail", "totalPage", "availPage", "totalVirt", "availVirt", "availExt")
            ]

        st = MemStatus()
        st.dwLength = ctypes.sizeof(MemStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined,unused-ignore]
            return ok({"total_bytes": int(st.total)})
        return error("GlobalMemoryStatusEx failed")
    return unavailable(f"no memory interface for {sys.platform}")


def numa(root: Path) -> Sensor:
    nodes_dir = root / "sys" / "devices" / "system" / "node"
    nodes = sorted(nodes_dir.glob("node[0-9]*")) if nodes_dir.exists() else []
    if not nodes:
        return unavailable("no /sys/devices/system/node (non-Linux or NUMA not exposed)")
    out = {}
    for node in nodes:
        cpulist = node / "cpulist"
        out[node.name] = _read(cpulist) if cpulist.exists() else None
    return ok({"nodes": len(nodes), "cpulists": out})


def affinity(_: Path) -> Sensor:
    getter = getattr(os, "sched_getaffinity", None)
    if getter is None:
        return unavailable(f"os.sched_getaffinity not available on {sys.platform} (M3 host provider)")
    return ok({"allowed_cpus": len(getter(0))})


def tpm(root: Path) -> Sensor:
    if sys.platform != "linux":
        return unavailable(f"TPM probe on {sys.platform} is an M3 host provider; not measured")
    dev = root / "sys" / "class" / "tpm" / "tpm0"
    if not dev.exists():
        return unavailable("no /sys/class/tpm/tpm0")
    version = dev / "tpm_version_major"
    pcr_dir = dev / "pcr-sha256"
    if not pcr_dir.exists():
        major = _read(version) if version.exists() else "unknown"
        return error(f"TPM present (version {major}) but kernel exposes no pcr-sha256 (needs Linux >= 5.12)")
    pcrs: dict[str, str] = {}
    for i in range(15):  # PCR 0-14, as in the Pillar 1 spec
        f = pcr_dir / str(i)
        try:
            pcrs[str(i)] = _read(f).lower()
        except OSError as exc:
            return error(f"PCR {i} unreadable: {exc.strerror}")
    # Pillar 1 correction: hash the raw register values, not a tool's stdout text.
    digest = hashlib.sha256(
        json.dumps({"bank": "sha256", "pcrs": pcrs}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ok({"version": _read(version) if version.exists() else None, "pcr_bank": "sha256", "pcr_digest": digest})


def ptp(root: Path) -> Sensor:
    ptp_dir = root / "sys" / "class" / "ptp"
    clocks = sorted(ptp_dir.glob("ptp[0-9]*")) if ptp_dir.exists() else []
    if not clocks:
        return unavailable("no PTP hardware clock (/sys/class/ptp); clock discipline is system time")
    names = {c.name: (_read(c / "clock_name") if (c / "clock_name").exists() else None) for c in clocks}
    virtual = sorted(n for n, label in names.items() if label and _VIRTUAL_PHC.search(label))
    # A PHC device existing does not mean the clock is disciplined. Drift needs ptp4l/pmc,
    # so it is reported as unmeasured, never as within the +/-10 ns envelope. Hypervisor PHCs
    # (Hyper-V, KVM, VMware) are paravirtual clocks, not IEEE 1588 hardware (QOS-0024).
    return ok(
        {
            "clocks": names,
            "virtual": virtual,
            "drift_ns": None,
            "drift_note": "unmeasured: requires ptp4l/pmc servo state",
        }
    )


def hugepages(root: Path) -> Sensor:
    meminfo = root / "proc" / "meminfo"
    if not meminfo.exists():
        return unavailable(f"no /proc/meminfo on {sys.platform}")
    text = _read(meminfo)
    total = re.search(r"^HugePages_Total:\s+(\d+)", text, re.M)
    size = re.search(r"^Hugepagesize:\s+(\d+) kB", text, re.M)
    if not total or not size:
        return unavailable("kernel reports no hugepage support")
    return ok({"pages": int(total.group(1)), "page_bytes": int(size.group(1)) * 1024})


def gpu(root: Path) -> Sensor:
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total,uuid", "--format=csv,noheader"])
    if out:
        gpus = [
            dict(zip(("name", "memory", "uuid"), (x.strip() for x in line.split(",")), strict=False))
            for line in out.splitlines()
        ]
        return ok({"vendor": "nvidia", "gpus": gpus})
    nv = root / "proc" / "driver" / "nvidia" / "gpus"
    if nv.exists():
        return error("NVIDIA driver present but nvidia-smi unavailable or failed")
    return unavailable("no NVIDIA GPU detected (other vendors: M3 host provider)")


_VIRTUAL_PHC = re.compile(r"hyperv|kvm|ptp_kvm|vmw|vmware|virtio", re.I)


def clock_discipline(ptp_sensor: Sensor) -> str:
    """'system' unless a non-virtual PHC exists. Even then it is only 'phc-unverified': a lock is never assumed."""
    if ptp_sensor["status"] != "OK":
        return "system"
    v = ptp_sensor["value"]
    hardware = [n for n in v["clocks"] if n not in v["virtual"]]
    return "phc-unverified" if hardware else "system"


SENSORS = {
    "cpu": cpu,
    "memory": memory,
    "numa": numa,
    "affinity": affinity,
    "tpm": tpm,
    "ptp": ptp,
    "hugepages": hugepages,
    "gpu": gpu,
}


def probe(root: Path = Path("/")) -> dict[str, Any]:
    """Run every sensor. ``root`` lets tests point sysfs/procfs at a synthetic tree."""
    sensors: dict[str, Sensor] = {}
    for name, fn in SENSORS.items():
        try:
            sensors[name] = fn(root)
        except Exception as exc:  # noqa: BLE001 - one broken sensor must not hide the others
            sensors[name] = error(f"{type(exc).__name__}: {exc}")
    discipline = clock_discipline(sensors["ptp"])
    return {
        "probe_version": 1,
        "os": sys.platform,
        "release": platform.release(),
        "python": platform.python_version(),
        "hostname_sha256": hashlib.sha256(platform.node().encode()).hexdigest()[:16],
        "clock_discipline": discipline,
        "sensors": sensors,
    }


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2, sort_keys=True))
