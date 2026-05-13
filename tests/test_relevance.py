"""_is_relevant filter for trials and papers.

False positives waste profile slots and pollute the orchestrator's context.
False negatives drop genuinely relevant items — the worse failure mode here.
"""
from __future__ import annotations


def test_net_paper_is_relevant(agent):
    paper = {
        "title": "PRRT with Lu-177-DOTATATE in metastatic neuroendocrine tumors",
        "journal": "Journal of Nuclear Medicine",
    }
    assert agent._is_relevant(paper, "paper") is True


def test_carcinoid_is_relevant(agent):
    paper = {
        "title": "Carcinoid syndrome management — a 2025 review",
        "journal": "Endocrine Reviews",
    }
    assert agent._is_relevant(paper, "paper") is True


def test_glioblastoma_paper_is_filtered(agent):
    paper = {
        "title": "Glioblastoma immunotherapy update",
        "journal": "Neuro-Oncology",
    }
    assert agent._is_relevant(paper, "paper") is False


def test_generic_melanoma_trial_is_filtered(agent):
    trial = {
        "title": "Pembrolizumab in metastatic melanoma",
        "brief_summary": "Anti-PD-1 therapy in advanced melanoma.",
        "eligibility_excerpt": "Stage IV melanoma.",
    }
    assert agent._is_relevant(trial, "trial") is False


def test_net_trial_with_dotatate_is_relevant(agent):
    trial = {
        "title": "Ac-225 DOTATATE in NET patients refractory to Lu-177",
        "brief_summary": "Alpha-PRRT in metastatic neuroendocrine tumors.",
        "eligibility_excerpt": "Histologically confirmed metastatic NET, prior Lu-177 PRRT.",
    }
    assert agent._is_relevant(trial, "trial") is True


def test_unrelated_drug_with_no_net_term_is_filtered(agent):
    item = {
        "title": "Atezolizumab in non-small cell lung cancer",
        "brief_summary": "Phase III RCT.",
    }
    assert agent._is_relevant(item, "paper") is False


def test_pancreatic_neuroendocrine_is_relevant(agent):
    # 'pancreatic cancer' is in exclusions, but 'neuroendocrine' in title overrides.
    item = {
        "title": "Everolimus in pancreatic neuroendocrine tumors",
        "brief_summary": "RCT of everolimus in pNET.",
    }
    assert agent._is_relevant(item, "paper") is True


def test_primary_site_net_is_relevant(agent):
    item = {
        "title": "Bronchopulmonary neuroendocrine tumor case series",
        "brief_summary": "Rare primary-site presentation of NET.",
    }
    assert agent._is_relevant(item, "paper") is True


def test_generic_non_net_cancer_is_filtered(agent):
    item = {
        "title": "PARP inhibitors in advanced carcinoma",
        "brief_summary": "Maintenance therapy in advanced solid tumors.",
    }
    assert agent._is_relevant(item, "paper") is False
