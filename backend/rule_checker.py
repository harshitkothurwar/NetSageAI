"""Deterministic Cisco show-command checks (regex, no LLM)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
IPV4 = rf"{IPV4_OCTET}(?:\.{IPV4_OCTET}){{3}}"

# Interface + IPv4 + optional /prefix (show ip interface brief / show run)
IFACE_IP_RE = re.compile(
    rf"(?P<iface>(?:GigabitEthernet|FastEthernet|Ethernet|Loopback|Serial|"
    rf"Vlan|Tunnel|Port-channel|Gi|Fa|Eth|Lo|Se|Vl|Tu|Po)"
    rf"[\w/.\-]*)\s+(?P<ip>{IPV4})(?:/(?P<prefix>\d{{1,2}}))?",
    re.IGNORECASE,
)

# ip address <ip> <mask>   OR   ip address <ip>/<prefix>
IP_ADDRESS_CMD_RE = re.compile(
    rf"ip\s+address\s+(?P<ip>{IPV4})(?:\s+(?P<mask>{IPV4})|/(?P<prefix>\d{{1,2}}))?",
    re.IGNORECASE,
)

ADMIN_DOWN_RE = re.compile(r"administratively\s+down", re.IGNORECASE)

LOOPBACK_RE = re.compile(r"^(?:Loopback|Lo)", re.IGNORECASE)


def check_show_output(show_output: str) -> dict[str, Any]:
    """Parse Cisco show text and return boolean flags plus messages."""
    text = show_output or ""
    flags: dict[str, bool] = {
        "duplicate_ip": False,
        "admin_down": False,
        "missing_mask": False,
        "slash32_anomaly": False,
    }
    messages: list[str] = []
    details: dict[str, Any] = {
        "duplicate_ips": [],
        "admin_down_interfaces": [],
        "missing_mask_entries": [],
        "slash32_interfaces": [],
    }

    # --- Duplicate IPv4 addresses (skip unassigned / 0.0.0.0) ---
    ip_to_ifaces: dict[str, set[str]] = defaultdict(set)
    for m in IFACE_IP_RE.finditer(text):
        ip = m.group("ip")
        if ip in {"0.0.0.0", "255.255.255.255"}:
            continue
        ip_to_ifaces[ip].add(m.group("iface"))

    # Also count bare "ip address" lines without an interface on the same line
    for m in IP_ADDRESS_CMD_RE.finditer(text):
        ip = m.group("ip")
        if ip in {"0.0.0.0", "255.255.255.255"}:
            continue
        ip_to_ifaces[ip].add("(config context)")

    true_dupes: dict[str, list[str]] = {}
    for ip, ifaces in ip_to_ifaces.items():
        real = [i for i in ifaces if i != "(config context)"]
        if len(real) >= 2:
            true_dupes[ip] = sorted(real)
        elif len(real) == 0 and text.lower().count(f"ip address {ip}") >= 2:
            true_dupes[ip] = ["(multiple ip address statements)"]

    if true_dupes:
        flags["duplicate_ip"] = True
        details["duplicate_ips"] = [
            {"ip": ip, "interfaces": ifaces} for ip, ifaces in true_dupes.items()
        ]
        for ip, ifaces in true_dupes.items():
            messages.append(f"Duplicate IP {ip} on {', '.join(ifaces)}.")

    # --- Administratively down (show ip int brief columns or "is administratively down") ---
    admin_ifaces: list[str] = []
    seen_admin: set[str] = set()
    for line in text.splitlines():
        if not ADMIN_DOWN_RE.search(line):
            continue
        first = line.split()[0] if line.split() else ""
        if not first or first.lower() in {"interface", "protocol"}:
            continue
        key = first.lower()
        if key not in seen_admin:
            seen_admin.add(key)
            admin_ifaces.append(first)
    if admin_ifaces:
        flags["admin_down"] = True
        details["admin_down_interfaces"] = admin_ifaces
        messages.append(
            "Administratively down: " + ", ".join(admin_ifaces) + "."
        )

    # --- Missing mask / prefix ---
    missing: list[str] = []
    for m in IP_ADDRESS_CMD_RE.finditer(text):
        ip = m.group("ip")
        mask = m.group("mask")
        prefix = m.group("prefix")
        if not mask and prefix is None:
            missing.append(ip)
    if missing:
        flags["missing_mask"] = True
        details["missing_mask_entries"] = missing
        messages.append(
            "Missing subnet mask on: " + ", ".join(missing) + "."
        )

    # --- /32 on non-loopback ---
    slash32: list[str] = []
    for m in IFACE_IP_RE.finditer(text):
        prefix = m.group("prefix")
        iface = m.group("iface")
        if prefix == "32" and not LOOPBACK_RE.match(iface):
            slash32.append(f"{iface} ({m.group('ip')}/32)")
    for m in IP_ADDRESS_CMD_RE.finditer(text):
        if m.group("prefix") == "32":
            slash32.append(f"{m.group('ip')}/32 (config)")
        elif m.group("mask") == "255.255.255.255":
            slash32.append(f"{m.group('ip')} mask 255.255.255.255")

    # Deduplicate slash32 labels
    slash32 = list(dict.fromkeys(slash32))
    if slash32:
        flags["slash32_anomaly"] = True
        details["slash32_interfaces"] = slash32
        messages.append(
            "/32 (host) mask on non-loopback or config: " + "; ".join(slash32) + "."
        )

    any_issue = any(flags.values())
    return {
        "ok": not any_issue,
        "flags": flags,
        "messages": messages,
        "details": details,
        "summary": (
            "No deterministic rule violations found."
            if not any_issue
            else " ".join(messages)
        ),
    }
