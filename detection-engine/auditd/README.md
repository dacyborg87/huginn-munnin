# auditd Detection Notes

Linux labs should use `auditd` to capture privileged command execution, sensitive file access, and authentication activity.

Recommended watch points:

```bash
-w /etc/passwd -p wa -k identity_change
-w /etc/shadow -p wa -k credential_store_access
-w /etc/sudoers -p wa -k privilege_config_change
-a always,exit -F arch=b64 -S execve -F euid=0 -k root_command
```

Map Linux audit activity to MITRE ATT&CK techniques in each lab README.
