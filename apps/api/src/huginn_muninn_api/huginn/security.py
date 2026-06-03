from collections import Counter

from huginn_muninn_api.schemas.security import SecurityAnalysisRequest, SecurityAnalysisResponse


class CybersecurityEngine:
    suspicious_terms = {
        "failed password": "Credential access: repeated authentication failure",
        "mimikatz": "Credential dumping indicator",
        "powershell -enc": "Obfuscated PowerShell execution",
        "beacon": "Possible command and control beaconing",
        "ransom": "Possible ransomware activity",
        "suricata": "Network IDS event",
        "wazuh": "Endpoint security event",
    }

    def analyze(self, request: SecurityAnalysisRequest) -> SecurityAnalysisResponse:
        content = request.content.lower()
        findings = [
            description for term, description in self.suspicious_terms.items() if term in content
        ]
        severity = self._severity(findings)
        mapped_tactics = self._map_tactics(findings)

        return SecurityAnalysisResponse(
            summary=self._summary(findings),
            severity=severity,
            findings=findings,
            mapped_tactics=mapped_tactics,
            recommendations=self._recommendations(severity, findings),
        )

    def _severity(self, findings: list[str]) -> str:
        count = len(findings)
        if count >= 3:
            return "high"
        if count >= 1:
            return "medium"
        return "informational"

    def _map_tactics(self, findings: list[str]) -> list[str]:
        tactics = Counter()
        for finding in findings:
            if "Credential" in finding:
                tactics["Credential Access"] += 1
            if "PowerShell" in finding:
                tactics["Execution"] += 1
            if "command and control" in finding:
                tactics["Command and Control"] += 1
            if "ransomware" in finding:
                tactics["Impact"] += 1
        return list(tactics)

    def _summary(self, findings: list[str]) -> str:
        if not findings:
            return "No suspicious indicators matched the current local rule set."
        return f"Matched {len(findings)} suspicious indicator(s) in the submitted content."

    def _recommendations(self, severity: str, findings: list[str]) -> list[str]:
        if not findings:
            return [
                "Preserve source logs for correlation.",
                "Add richer Wazuh, Suricata, endpoint, or cloud telemetry for analysis.",
            ]

        recommendations = [
            "Validate affected hosts and user accounts.",
            "Correlate timestamps across endpoint, network, and identity logs.",
            "Preserve evidence before containment actions.",
        ]
        if severity == "high":
            recommendations.append("Escalate to incident response and begin containment planning.")
        return recommendations
