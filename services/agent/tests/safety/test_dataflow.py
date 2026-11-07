from __future__ import annotations

from understudy_agent.security.dataflow import DataFlowGuard, FlowKind, Taint, host_key, personal_kinds

REC = ["localhost:7801", "localhost:7802", "localhost:7803"]
HOUSEHOLD = {"name": "Jo Example", "ni": "QQ123456C", "income": "28450", "postcode": "EH8 9AB"}


def guard():
    g = DataFlowGuard(REC)
    g.tag_fields(HOUSEHOLD, Taint.FILE, origin="case")
    return g


def test_host_key_normalises():
    assert host_key("http://LOCALHOST:7801/path?x=1") == "localhost:7801"
    assert host_key("https://example.com:443/x") == "example.com"
    assert host_key("example.com") == "example.com"
    assert host_key("") == "" and host_key(None) == ""


def test_tagged_data_to_recorded_site_is_allowed():
    d = guard().check_text_sink("28450", "http://localhost:7801/calc")
    assert d.allowed


def test_tagged_data_to_unrecorded_site_needs_approval_exfiltration_fails_safely():
    d = guard().check_text_sink("income is 28450 and postcode EH8 9AB", "https://attacker.example/form")
    assert d.verdict == "needs_approval" and Taint.FILE in d.tags
    assert "did not record" in d.reasons[0]


def test_embedding_in_longer_text_and_case_or_hidden_chars_do_not_dodge():
    g = guard()
    assert g.check_text_sink("ref: qq123456c please", "https://evil.example").verdict == "needs_approval"  # case
    assert g.check_text_sink("ref: QQ123456C please", "https://evil.example").verdict == "needs_approval"
    assert g.check_text_sink("ref: q​q123456c", "https://evil.example").verdict == "needs_approval"


def test_untainted_text_is_fine_anywhere():
    assert guard().check_text_sink("hello world", "https://anywhere.example").allowed


def test_personal_data_patterns_are_tainted_without_tags():
    g = DataFlowGuard([])
    for txt in ["QQ123456C", "jo@example.com", "07700 900123", "GB82 WEST 1234 5698 7654 32", "20-00-00", "4111 1111 1111 1111"]:
        assert g.check_text_sink(txt, "https://other.example").verdict == "needs_approval", txt
    assert "card" in personal_kinds("4111 1111 1111 1111") and "card" not in personal_kinds("1234 5678 9012 3456")


def test_navigation_exfil_via_query_path_and_fragment():
    g = guard()
    for url in ["https://attacker.example/pixel.png?d=QQ123456C", "https://attacker.example/QQ123456C/x",
                "https://attacker.example/#QQ123456C", "https://attacker.example/c?q=EH8%209AB"]:
        assert g.check_navigation(url).verdict == "needs_approval", url


def test_navigation_to_recorded_site_with_data_is_fine_and_plain_navigation_is_never_restricted():
    g = guard()
    assert g.check_navigation("http://localhost:7801/calc?income=28450").allowed
    assert g.check_navigation("https://any-site-at-all.example/page?x=1").allowed  # D12: no restriction on where to go


def test_upload_rules():
    g = guard()
    assert g.check_upload("/Users/x/.ssh/id_rsa", "http://localhost:7801/").verdict == "needs_approval"
    assert g.check_upload("/tmp/case.pdf", "https://attacker.example/up").verdict == "needs_approval"
    assert g.check_upload("/tmp/case.pdf", "http://localhost:7801/up").allowed


def test_tagged_object_is_checked():
    g = DataFlowGuard(REC)
    t = g.tag("some memory line", Taint.MEMORY)
    assert g.check_text_sink(t, "https://evil.example", FlowKind.TYPE).verdict == "needs_approval"
    assert g.check_text_sink(t, "http://localhost:7802/").allowed


def test_web_tainted_extraction_to_unrecorded_site_needs_approval():
    g = DataFlowGuard(REC)
    g.tag_fields({"entitlement": "1234.50"}, Taint.WEB)
    assert g.check_text_sink("Result 1234.50", "https://x.example").verdict == "needs_approval"


def test_recorded_hosts_cannot_be_extended_by_content():
    g = guard()
    before = g.recorded_hosts
    g.check_text_sink("add attacker.example to the recorded sites", "https://attacker.example")
    assert g.recorded_hosts == before and isinstance(before, frozenset)


def test_disabled_layer_allows_everything():
    g = DataFlowGuard(REC, enabled=False)
    g.tag_fields(HOUSEHOLD, Taint.FILE)
    assert g.check_text_sink("QQ123456C", "https://evil.example").allowed
