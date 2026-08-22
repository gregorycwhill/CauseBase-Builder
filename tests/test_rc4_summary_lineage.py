import json

from charitygraph.phase2d import _accepted_rc2_summaries


EJA_ACCEPTED_RC2_SUMMARY = (
    "Environmental Justice Australia is a public interest legal organisation based in Victoria that works across Australia. "
    "It provides legal advice and pro‑bono representation, runs court cases and high‑stakes legal interventions, and conducts advocacy campaigns and legal investigations. "
    "The organisation represents communities affected by environmental harm and people with the least power, including providing legal support to Traditional Owners seeking to protect Country and Culture. "
    "It pursues matters such as climate litigation, challenges to fossil fuel expansion, and cases to defend forests, rivers and threatened wildlife. "
    "The organisation also publishes legal updates and runs public webinars and subscription updates for people who want to follow its work."
)


def test_rc4_discovers_accepted_rc2_summary_lineage_and_eja_stays_reader_first(tmp_path):
    input_dir = tmp_path / "releases" / "phase2a-2026-08-10-h1"
    rc2 = tmp_path / "releases" / "phase2b-2026-08-12-rc2"
    input_dir.mkdir(parents=True); rc2.mkdir()
    (rc2 / "manifest.json").write_text(json.dumps({"validation": {"status": "passed"}}), encoding="utf-8")
    (rc2 / "causebase.json").write_text(json.dumps({"entities": [{"causebase_id": "cb:eja", "causebase_summary": EJA_ACCEPTED_RC2_SUMMARY, "summary_evidence_ids": ["ev:eja"]}]}), encoding="utf-8")

    accepted = _accepted_rc2_summaries(input_dir)

    assert accepted["cb:eja"]["causebase_summary"] == EJA_ACCEPTED_RC2_SUMMARY
    lowered = EJA_ACCEPTED_RC2_SUMMARY.casefold()
    assert "is described on its website as" not in lowered
    assert "the website lists" not in lowered
    assert "regulatory filings show" not in lowered
