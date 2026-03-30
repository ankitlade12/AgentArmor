import time
import json
import threading
from typing import Optional, List, Dict, Any
from ..hooks import ResponseContext


# Compliance framework control mappings
COMPLIANCE_CONTROLS = {
    "soc2": {
        "CC6.1": {
            "name": "Logical and Physical Access Controls",
            "modules": ["shield", "ml_shield", "unicode_shield", "tool_firewall", "mcp_firewall", "hitl_gate"],
            "description": "Controls to restrict logical access to systems and data",
        },
        "CC6.6": {
            "name": "Security Event Monitoring",
            "modules": ["recorder", "cot_auditor", "latency_breaker"],
            "description": "Measures to detect anomalies and security events",
        },
        "CC6.7": {
            "name": "Data Transmission Controls",
            "modules": ["filter", "exfiltration_guard", "canary"],
            "description": "Controls over data in transit and at rest",
        },
        "CC6.8": {
            "name": "Unauthorized Software Prevention",
            "modules": ["code_shield", "tool_firewall"],
            "description": "Controls to prevent unauthorized or malicious software",
        },
        "CC7.2": {
            "name": "System Monitoring",
            "modules": ["budget", "rate_limiter", "latency_breaker", "cost_tags"],
            "description": "Monitoring of system components for anomalies",
        },
        "CC8.1": {
            "name": "Change Management",
            "modules": ["recorder", "hitl_gate"],
            "description": "Authorization and documentation of changes",
        },
    },
    "hipaa": {
        "164.312(a)(1)": {
            "name": "Access Control",
            "modules": ["shield", "ml_shield", "tool_firewall", "hitl_gate"],
            "description": "Technical controls to allow access only to authorized persons",
        },
        "164.312(a)(2)(iv)": {
            "name": "Encryption and Decryption",
            "modules": ["filter", "exfiltration_guard"],
            "description": "Mechanism to encrypt and decrypt ePHI",
        },
        "164.312(b)": {
            "name": "Audit Controls",
            "modules": ["recorder", "cost_tags", "cot_auditor"],
            "description": "Hardware, software, and procedures to record and examine access",
        },
        "164.312(c)(1)": {
            "name": "Integrity Controls",
            "modules": ["grounding", "canary", "code_shield"],
            "description": "Policies to protect ePHI from improper alteration or destruction",
        },
        "164.312(d)": {
            "name": "Person or Entity Authentication",
            "modules": ["hitl_gate"],
            "description": "Procedures to verify identity of persons seeking access",
        },
        "164.312(e)(1)": {
            "name": "Transmission Security",
            "modules": ["filter", "exfiltration_guard", "canary"],
            "description": "Technical measures to guard against unauthorized access during transmission",
        },
    },
    "gdpr": {
        "Art.5(1)(f)": {
            "name": "Integrity and Confidentiality",
            "modules": ["filter", "exfiltration_guard", "shield", "ml_shield"],
            "description": "Appropriate security including protection against unauthorized processing",
        },
        "Art.25": {
            "name": "Data Protection by Design",
            "modules": ["filter", "canary", "code_shield", "toxicity"],
            "description": "Implementing data protection principles by design and default",
        },
        "Art.30": {
            "name": "Records of Processing Activities",
            "modules": ["recorder", "cost_tags", "budget"],
            "description": "Maintaining records of all processing activities",
        },
        "Art.32": {
            "name": "Security of Processing",
            "modules": ["shield", "ml_shield", "tool_firewall", "mcp_firewall", "rate_limiter"],
            "description": "Technical and organizational measures for appropriate security",
        },
        "Art.33": {
            "name": "Breach Notification",
            "modules": ["exfiltration_guard", "canary", "cot_auditor"],
            "description": "Notification of data breaches to supervisory authority",
        },
        "Art.35": {
            "name": "Data Protection Impact Assessment",
            "modules": ["grounding", "toxicity", "semantic_drift"],
            "description": "Assessment of impact of processing on data protection",
        },
    },
}


class ComplianceReporterModule:
    """Generates compliance reports mapped to SOC2, HIPAA, and GDPR frameworks."""

    def __init__(self, frameworks: Optional[List[str]] = None,
                 organization: str = "Unknown",
                 session_id: Optional[str] = None,
                 auto_track: bool = True):
        """
        Args:
            frameworks: List of compliance frameworks to report on ('soc2', 'hipaa', 'gdpr')
            organization: Organization name for reports
            session_id: Unique session identifier
            auto_track: Whether to auto-track events via post_response hook
        """
        self.frameworks = frameworks or ["soc2", "hipaa", "gdpr"]
        self.organization = organization
        self.session_id = session_id or f"session_{int(time.time())}"
        self.auto_track = auto_track
        self._lock = threading.Lock()

        self.session_start = time.time()
        self.events: List[Dict[str, Any]] = []
        self.data_handling_events: List[Dict[str, Any]] = []
        self._request_count = 0

    def post_record(self, ctx: ResponseContext) -> ResponseContext:
        """Post-response hook: track events for compliance reporting."""
        if not self.auto_track:
            return ctx
        with self._lock:
            self._request_count += 1
            event = {
                "timestamp": time.time(),
                "request_number": self._request_count,
                "model": ctx.model,
                "provider": ctx.provider,
                "latency_ms": ctx.latency_ms,
                "has_usage": ctx.usage is not None,
            }
            self.events.append(event)
        return ctx

    def record_data_event(self, event_type: str, details: str,
                          module: str = "", severity: str = "info") -> None:
        """Record a data handling event for compliance tracking."""
        with self._lock:
            self.data_handling_events.append({
                "timestamp": time.time(),
                "type": event_type,
                "details": details,
                "module": module,
                "severity": severity,
            })

    def generate_report(self, module_reports: Optional[Dict[str, Any]] = None,
                        framework: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a compliance report.

        Args:
            module_reports: Dict of module name -> module report (from ArmorCore.report())
            framework: Specific framework to report on (None = all configured)
        """
        frameworks_to_report = [framework] if framework else self.frameworks
        module_reports = module_reports or {}
        framework_reports = {
            fw: self._evaluate_framework(fw, module_reports)
            for fw in frameworks_to_report
            if fw in COMPLIANCE_CONTROLS
        }

        report = {
            "report_metadata": {
                "generated_at": time.time(),
                "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "organization": self.organization,
                "session_id": self.session_id,
                "session_start": self.session_start,
                "session_duration_seconds": time.time() - self.session_start,
                "frameworks": frameworks_to_report,
                "agentarmor_version": "1.1.0",
            },
            "summary": self._generate_summary(module_reports, framework_reports),
            "frameworks": framework_reports,
            "data_handling": {
                "events_count": len(self.data_handling_events),
                "events": self.data_handling_events[-50:],
            },
            "active_modules": list(module_reports.keys()),
            "request_stats": {
                "total_requests": self._request_count,
                "session_events": len(self.events),
            },
        }

        return report

    def _generate_summary(
        self,
        module_reports: Dict[str, Any],
        framework_reports: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate executive summary."""
        active_modules = set(module_reports.keys())
        total_controls = 0
        compliant_controls = 0
        partial_controls = 0
        non_compliant_controls = 0

        for fw_report in framework_reports.values():
            fw_summary = fw_report.get("summary", {})
            total_controls += fw_summary.get("total_controls", 0)
            compliant_controls += fw_summary.get("compliant", 0)
            partial_controls += fw_summary.get("partial", 0)
            non_compliant_controls += fw_summary.get("non_compliant", 0)

        covered_controls = compliant_controls + partial_controls
        weighted_score = compliant_controls + (0.5 * partial_controls)
        coverage_pct = (weighted_score / total_controls * 100) if total_controls > 0 else 0

        # Count security events from module reports
        security_events = 0
        for mod_name, mod_report in module_reports.items():
            if isinstance(mod_report, dict):
                security_events += mod_report.get("detections", 0)
                security_events += mod_report.get("alerts", 0)
                security_events += mod_report.get("violations", 0)

        return {
            "compliance_score": round(coverage_pct, 1),
            "controls_total": total_controls,
            "controls_covered": covered_controls,
            "controls_compliant": compliant_controls,
            "controls_partial": partial_controls,
            "controls_non_compliant": non_compliant_controls,
            "active_modules": len(active_modules),
            "security_events_total": security_events,
            "data_handling_events": len(self.data_handling_events),
            "risk_level": self._assess_risk_level(coverage_pct, security_events),
        }

    def _assess_risk_level(self, coverage: float, events: int) -> str:
        """Assess overall risk level."""
        if coverage >= 80 and events == 0:
            return "low"
        elif coverage >= 60:
            return "medium"
        elif coverage >= 40:
            return "high"
        return "critical"

    def _evaluate_framework(self, framework: str,
                            module_reports: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate compliance for a specific framework."""
        controls = COMPLIANCE_CONTROLS.get(framework, {})
        active_modules = set(module_reports.keys())

        control_results = {}
        compliant_count = 0
        partial_count = 0
        non_compliant_count = 0

        for control_id, control in controls.items():
            required_modules = set(control["modules"])
            active_for_control = required_modules & active_modules
            coverage = len(active_for_control) / len(required_modules) if required_modules else 0

            # Gather findings from active modules
            findings = []
            for mod_name in active_for_control:
                mod_report = module_reports.get(mod_name, {})
                if isinstance(mod_report, dict):
                    detections = mod_report.get("detections", 0)
                    if detections > 0:
                        findings.append(f"{mod_name}: {detections} detection(s)")

            if coverage >= 0.7:
                status = "compliant"
                compliant_count += 1
            elif coverage > 0:
                status = "partial"
                partial_count += 1
            else:
                status = "non_compliant"
                non_compliant_count += 1

            control_results[control_id] = {
                "name": control["name"],
                "description": control["description"],
                "status": status,
                "coverage": round(coverage * 100, 1),
                "required_modules": sorted(required_modules),
                "active_modules": sorted(active_for_control),
                "missing_modules": sorted(required_modules - active_modules),
                "findings": findings,
            }

        return {
            "framework": framework,
            "controls": control_results,
            "summary": {
                "total_controls": len(controls),
                "compliant": compliant_count,
                "partial": partial_count,
                "non_compliant": non_compliant_count,
                "compliance_percentage": round(
                    compliant_count / len(controls) * 100 if controls else 0, 1
                ),
            },
        }

    def export_json(self, module_reports: Optional[Dict[str, Any]] = None,
                    filepath: Optional[str] = None) -> str:
        """Export compliance report as JSON string, optionally to file."""
        report = self.generate_report(module_reports)
        json_str = json.dumps(report, indent=2, default=str)
        if filepath:
            with open(filepath, 'w') as f:
                f.write(json_str)
        return json_str

    def report(self) -> dict:
        with self._lock:
            return {
                "session_id": self.session_id,
                "frameworks": self.frameworks,
                "requests_tracked": self._request_count,
                "data_events": len(self.data_handling_events),
                "session_duration": time.time() - self.session_start,
            }
