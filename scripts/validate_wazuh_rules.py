from pathlib import Path
from xml.etree import ElementTree


RULE_DIR = Path("detection-engine/wazuh/rules")


def main() -> None:
    failures: list[str] = []
    seen_ids: set[str] = set()

    for rule_file in sorted(RULE_DIR.glob("*.xml")):
        try:
            root = ElementTree.parse(rule_file).getroot()
        except ElementTree.ParseError as exc:
            failures.append(f"{rule_file}: XML parse error: {exc}")
            continue

        for rule in root.findall(".//rule"):
            rule_id = rule.attrib.get("id")
            if not rule_id:
                failures.append(f"{rule_file}: rule missing id")
                continue
            if rule_id in seen_ids:
                failures.append(f"{rule_file}: duplicate rule id {rule_id}")
            seen_ids.add(rule_id)

            mitre_ids = [node.text for node in rule.findall("./mitre/id") if node.text]
            if not mitre_ids:
                failures.append(f"{rule_file}: rule {rule_id} missing MITRE mapping")

    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)

    print(f"Validated {len(seen_ids)} Wazuh rule(s).")


if __name__ == "__main__":
    main()
