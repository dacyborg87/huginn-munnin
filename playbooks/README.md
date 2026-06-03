# Playbooks

SOC playbooks define repeatable triage and escalation procedures.

Current playbooks:

- [Account lockout](account-lockout.md)
- [Network containment](network-containment.md)
- [Windows brute-force triage](windows-bruteforce-triage.md)

Playbook selection is handled by `core/detection_response_map.py` after a detection has been normalized into a canonical SOC event.
