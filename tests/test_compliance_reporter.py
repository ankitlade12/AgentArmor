import pytest
import json
import agentarmor
from agentarmor.modules.compliance_reporter import ComplianceReporterModule, COMPLIANCE_CONTROLS
from agentarmor.hooks import ResponseContext, RequestContext


def make_response_ctx(text="test response"):
    req = RequestContext(messages=[{"role": "user", "content": "test"}], model="gpt-4o")
    return ResponseContext(text=text, model="gpt-4o", provider="openai", request=req)


class TestReportGeneration:
    def test_basic_report(self):
        module = ComplianceReporterModule(organization="TestCorp")
        report = module.generate_report({})
        assert report["report_metadata"]["organization"] == "TestCorp"
        assert "summary" in report
        assert "frameworks" in report

    def test_report_with_module_data(self):
        module = ComplianceReporterModule(frameworks=["soc2"])
        module_reports = {
            "shield": {"detections": 3, "samples": []},
            "filter": {"redacted": 5},
            "recorder": {"entries": 10},
        }
        report = module.generate_report(module_reports)
        assert "soc2" in report["frameworks"]
        assert report["summary"]["active_modules"] == 3

    def test_all_frameworks(self):
        module = ComplianceReporterModule(frameworks=["soc2", "hipaa", "gdpr"])
        report = module.generate_report({})
        assert "soc2" in report["frameworks"]
        assert "hipaa" in report["frameworks"]
        assert "gdpr" in report["frameworks"]

    def test_single_framework(self):
        module = ComplianceReporterModule()
        report = module.generate_report({}, framework="gdpr")
        assert "gdpr" in report["frameworks"]
        assert report["summary"]["controls_total"] == len(COMPLIANCE_CONTROLS["gdpr"])


class TestComplianceScoring:
    def test_zero_coverage(self):
        module = ComplianceReporterModule(frameworks=["soc2"])
        report = module.generate_report({})
        summary = report["summary"]
        assert summary["compliance_score"] == 0.0
        assert summary["controls_covered"] == 0

    def test_partial_coverage(self):
        module = ComplianceReporterModule(frameworks=["soc2"])
        module_reports = {"shield": {"detections": 0}, "recorder": {"entries": 5}}
        report = module.generate_report(module_reports)
        summary = report["summary"]
        assert summary["controls_covered"] > 0
        assert summary["compliance_score"] > 0
        assert summary["controls_compliant"] == 0
        assert summary["controls_partial"] == 3

    def test_risk_assessment(self):
        module = ComplianceReporterModule(frameworks=["soc2"])
        # No coverage = critical
        report = module.generate_report({})
        assert report["summary"]["risk_level"] == "critical"


class TestControlEvaluation:
    def test_compliant_control(self):
        module = ComplianceReporterModule(frameworks=["soc2"])
        # CC6.8 requires: code_shield, tool_firewall - provide both
        module_reports = {
            "code_shield": {"detections": 0},
            "tool_firewall": {"blocked": 0},
        }
        report = module.generate_report(module_reports)
        cc68 = report["frameworks"]["soc2"]["controls"]["CC6.8"]
        assert cc68["status"] == "compliant"
        assert cc68["coverage"] == 100.0

    def test_partial_control(self):
        module = ComplianceReporterModule(frameworks=["soc2"])
        # CC6.1 requires multiple modules - provide only one
        module_reports = {"shield": {"detections": 0}}
        report = module.generate_report(module_reports)
        cc61 = report["frameworks"]["soc2"]["controls"]["CC6.1"]
        assert cc61["status"] in ("partial", "non_compliant")

    def test_non_compliant_control(self):
        module = ComplianceReporterModule(frameworks=["hipaa"])
        report = module.generate_report({})
        for control_id, control in report["frameworks"]["hipaa"]["controls"].items():
            assert control["status"] == "non_compliant"

    def test_findings_included(self):
        module = ComplianceReporterModule(frameworks=["soc2"])
        module_reports = {"shield": {"detections": 5, "samples": ["test"]}}
        report = module.generate_report(module_reports)
        cc61 = report["frameworks"]["soc2"]["controls"]["CC6.1"]
        assert len(cc61["findings"]) > 0


class TestEventTracking:
    def test_post_record(self):
        module = ComplianceReporterModule()
        ctx = make_response_ctx()
        module.post_record(ctx)
        assert module._request_count == 1
        assert len(module.events) == 1

    def test_post_record_respects_auto_track(self):
        module = ComplianceReporterModule(auto_track=False)
        ctx = make_response_ctx()
        module.post_record(ctx)
        assert module._request_count == 0
        assert len(module.events) == 0

    def test_data_event_recording(self):
        module = ComplianceReporterModule()
        module.record_data_event("pii_detected", "Email found in output", module="filter", severity="warning")
        assert len(module.data_handling_events) == 1
        assert module.data_handling_events[0]["type"] == "pii_detected"

    def test_data_events_in_report(self):
        module = ComplianceReporterModule()
        module.record_data_event("pii_redacted", "SSN redacted", module="filter")
        report = module.generate_report({})
        assert report["data_handling"]["events_count"] == 1


class TestExport:
    def test_json_export(self):
        module = ComplianceReporterModule(organization="TestCorp")
        json_str = module.export_json({})
        data = json.loads(json_str)
        assert data["report_metadata"]["organization"] == "TestCorp"

    def test_json_export_to_file(self, tmp_path):
        module = ComplianceReporterModule()
        filepath = str(tmp_path / "report.json")
        module.export_json({}, filepath=filepath)
        with open(filepath) as f:
            data = json.loads(f.read())
        assert "summary" in data


class TestReport:
    def test_module_report(self):
        module = ComplianceReporterModule(organization="Test")
        report = module.report()
        assert "session_id" in report
        assert "frameworks" in report
        assert report["requests_tracked"] == 0


class TestVersionField:
    def test_version_is_dynamic_not_hardcoded(self):
        """Version in the report must track the installed package, not a frozen string."""
        module = ComplianceReporterModule()
        report = module.generate_report({})
        version = report["report_metadata"]["agentarmor_version"]
        assert version != "1.1.0", "version must no longer be hardcoded to 1.1.0"
        assert version != "unknown"

    def test_version_matches_package_metadata(self):
        from importlib.metadata import version as pkg_version

        module = ComplianceReporterModule()
        report = module.generate_report({})
        assert report["report_metadata"]["agentarmor_version"] == pkg_version("agentarmor")


class TestGdprArt35Mapping:
    def test_art35_includes_semantic_drift(self):
        """semantic_drift is a real module post-1.3.0 and must appear in Art.35 controls."""
        art35 = COMPLIANCE_CONTROLS["gdpr"]["Art.35"]
        assert "semantic_drift" in art35["modules"]

    def test_art35_covers_breadth_of_dpia_signals(self):
        art35 = COMPLIANCE_CONTROLS["gdpr"]["Art.35"]
        for expected in ("grounding", "toxicity", "semantic_drift", "cot_auditor"):
            assert expected in art35["modules"], f"{expected} missing from Art.35"

    def test_art35_coverage_counts_with_drift_enabled(self):
        """Enabling the drift module must count toward Art.35 coverage."""
        module = ComplianceReporterModule(frameworks=["gdpr"])
        report = module.generate_report({"semantic_drift": {"turns_analyzed": 5}})
        art35_entry = report["frameworks"]["gdpr"]["controls"]["Art.35"]
        assert "semantic_drift" in art35_entry["active_modules"]


class TestInitIntegration:
    def teardown_method(self):
        agentarmor.teardown()

    def test_compliance_is_additive(self):
        core = agentarmor.init(
            compliance=True,
            unicode_shield=True,
            hitl_gate=True,
            exfiltration_guard=True,
            privilege_escalation=True,
        )
        assert "compliance" in core.modules
        assert "unicode_shield" in core.modules
        assert "hitl_gate" in core.modules
        assert "exfiltration_guard" in core.modules
        assert "privilege_escalation" in core.modules
