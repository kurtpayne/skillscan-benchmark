"""SkillGate (charliechenye/SkillGate, MIT) adapter — a FOSS, pure-STATIC scanner.

Per its own README it "does not execute repository code, start MCP servers, call LLMs, or install
remote packages" — files-only static analysis. Verified in the sandbox (2026-06-17): runs in 1-2s and
needs NO network (identical output under `unshare -n`), so we grade it fully OFFLINE.

Verdict = SkillGate's OWN deployable gate, not a hand-rolled heuristic: `skillgate check --policy <P>
--format json` → `policy_result.blocked`. That is the tool's "should I install this skill" decision,
the apples-to-apples analogue of SkillSpector CRITICAL/HIGH → block. We use the **preinstall** policy
profile (generated via `skillgate policy init --profile preinstall`) because the board's scenario IS
pre-install screening. (An earlier draft mapped `scan` SARIF `level:error` → malicious; that's the
findings *inventory*, not the gate — it over-flagged benign base skills like document-skills/calendar,
so it was replaced by the policy gate.)

Untrusted day-old third-party code: runs ONLY inside the ephemeral Firecracker (Fly Machines) sandbox,
never on a real host, and each scan is network-isolated via `unshare -n` (no egress) with a per-scan
timeout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from ..model import ScanResult, Verdict
from .base import ScannerAdapter


class SkillGateAdapter(ScannerAdapter):
    name = "skillgate"

    def __init__(self, binary: str, version: str = "unknown", timeout_s: int = 90, policy: str = "skillgate.yaml"):
        super().__init__(binary, version, timeout_s)
        self.policy = policy
        # Cut egress for this untrusted tool: give each scan its own empty network namespace.
        # `unshare -n` needs CAP_SYS_ADMIN (present in the Fly machine, root). Set
        # SCOREBOARD_SKILLGATE_NETCUT=0 when the runner already isolates the network (e.g. a
        # `docker run --network none` container, where unshare -n would fail for lack of caps).
        netcut_on = os.environ.get("SCOREBOARD_SKILLGATE_NETCUT", "1") != "0"
        self._netcut = ["unshare", "-n"] if (netcut_on and shutil.which("unshare")) else []

    def _argv(self, skill_path: str) -> list[str]:
        return [*self._netcut, self.binary, "check", skill_path, "--policy", self.policy, "--format", "json"]

    def _parse(self, sample_id: str, proc: subprocess.CompletedProcess) -> ScanResult:
        try:
            s = proc.stdout
            d = json.loads(s) if s.lstrip().startswith("{") else json.loads(s[s.find("{") : s.rfind("}") + 1])
        except Exception as e:  # noqa: BLE001
            return ScanResult(
                sample_id,
                self.name,
                self.version,
                Verdict.ERROR,
                error=f"no/invalid json: {str(e)[:120]}; stderr={proc.stderr[:120]}",
            )
        pr = d.get("policy_result", {}) or {}
        blocked = bool(pr.get("blocked"))
        sev = ((d.get("scan_report", {}) or {}).get("summary", {}) or {}).get("findings_by_severity", {}) or {}
        cats = sorted({(v.get("rule_id") or v.get("ruleId") or "").lower() for v in pr.get("violations", [])} - {""})
        return ScanResult(
            sample_id,
            self.name,
            self.version,
            Verdict.MALICIOUS if blocked else Verdict.BENIGN,
            severity="blocked" if blocked else "",
            categories=cats,
            raw={"blocked": blocked, "violations": len(pr.get("violations", [])), "severity": sev},
        )
