"""Detection-to-response mapping for SOC event routing.

This layer maps normalized detection names or MITRE techniques to analyst
playbooks. It does not modify detection rules; it only routes events after
alerts are generated.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.event_schema import SocEvent


@dataclass(frozen=True)
class PlaybookRoute:
    route_id: str
    playbook_path: str
    reason: str
    priority: str


DETECTION_NAME_ROUTES: dict[str, PlaybookRoute] = {
    "SOC-WIN-AUTH-BRUTEFORCE-001": PlaybookRoute(
        route_id="route.windows_bruteforce.account_lockout",
        playbook_path="playbooks/account-lockout.md",
        reason="Repeated Windows authentication failures indicate a brute-force attempt.",
        priority="high",
    ),
    "SOC-NET-SMB-PROBE-001": PlaybookRoute(
        route_id="route.smb_probe.network_containment",
        playbook_path="playbooks/network-containment.md",
        reason="SMB probing may indicate discovery or lateral movement preparation.",
        priority="medium",
    ),
}


MITRE_ROUTES: dict[str, PlaybookRoute] = {
    "T1110": PlaybookRoute(
        route_id="route.mitre_t1110.account_lockout",
        playbook_path="playbooks/account-lockout.md",
        reason="MITRE T1110 maps to brute force credential access.",
        priority="high",
    ),
    "T1046": PlaybookRoute(
        route_id="route.mitre_t1046.network_containment",
        playbook_path="playbooks/network-containment.md",
        reason="MITRE T1046 maps to network service discovery.",
        priority="medium",
    ),
}


DEFAULT_ROUTE = PlaybookRoute(
    route_id="route.default.tier1_triage",
    playbook_path="playbooks/README.md",
    reason="No exact detection mapping found; route to general SOC triage.",
    priority="low",
)


def resolve_playbook_route(event: SocEvent) -> PlaybookRoute:
    detection_name = str(event.normalized_context.get("detection_name", ""))
    if detection_name in DETECTION_NAME_ROUTES:
        return DETECTION_NAME_ROUTES[detection_name]

    for mapping in event.mitre_mapping:
        route = MITRE_ROUTES.get(mapping.technique_id)
        if route:
            return route

    return DEFAULT_ROUTE
