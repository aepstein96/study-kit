"""Classify clinical-trial primary endpoints: surrogate vs outcome vs symptom-scale, plus
oncology's endpoint families and per-disease-area condition matchers.

The taxonomy mirrors Zhang 2020's three
endpoint classes, applied to primary-outcome TITLES. Order matters: the surrogate
"…-free survival" family must match before the generic "survival", and specific event words
before scale words. ``demo()`` holds the synthetic known-answer checks; registry-dependent
known-answers (real NCTs) live in each study's own verification.
"""
from __future__ import annotations

import re

EP_SURROGATE = re.compile(
    r"progression[- ]free|event[- ]free|disease[- ]free|recurrence[- ]free|relapse[- ]free"
    r"|failure[- ]free|objective response|overall response|response rate|complete response"
    r"|complete remission|cytogenetic|sustained virologic|svr|viral|virologic|rna|hiv[- ]1 rna"
    r"|hba1c|a1c|glycosylated|glucose|cholesterol|ldl|hdl|triglyceride|blood pressure"
    r"|systolic|diastolic|egfr|creatinine|albuminuria|fev ?1|forced expiratory|bone mineral"
    r"|densit|hemoglobin|platelet|neutrophil|cd4|antibod|titer|seroconversion|seroresponse"
    r"|immunogenic|pharmacokinetic|auc\b|cmax|concentration|uric acid|testosterone|estradiol"
    r"|ige\b|eosinophil|c[- ]reactive|crp\b|biomarker|tumor size|lesion count|intraocular pressure"
    r"|viral load|pasi ?(75|90|100)|clearance rate", re.I)
EP_OUTCOME = re.compile(
    r"death|mortality|survival|stroke|myocardial infarction|\bmi\b|mace|cardiovascular event"
    r"|coronary event|heart failure event|hospitali[sz]ation|hospitali[sz]ed|exacerbation"
    r"|fracture|venous thromboembolism|thromboembolic|pulmonary embolism|deep vein"
    r"|amputation|transplant|dialysis|end[- ]stage|relapse|recurrence\b|rejection"
    r"|progression to (type 2 )?diabetes|aids[- ]defining|treatment failure|composite of",
    re.I)
EP_SCALE = re.compile(
    r"\bscore|scale|index\b|questionnaire|panss|madrs|ham[- ]?[ad]|ymrs|cgi\b|adas[- ]cog"
    r"|updrs|edss|acr ?20|acr ?50|das ?28|pasi\b|easi\b|iga\b|symptom|pain|pruritus|itch"
    r"|quality of life|function(al)? (status|capacity)|6[- ]min|walk test|responder"
    r"|remission\b|severity|improvement", re.I)


def endpoint_class(titles: list[str]) -> str:
    """One class per trial from its PRIMARY outcome titles.

    Precedence surrogate-family check first (inside each title), then classes by strength:
    any outcome-event title makes the trial an outcome trial (co-primary OS + PFS counts as
    outcome); else any scale title; else any surrogate; else unclassified.
    """
    classes = []
    for t in titles:
        # "...-free survival" etc. are surrogates even though they contain "survival"
        if EP_SURROGATE.search(t):
            classes.append("surrogate")
        elif EP_OUTCOME.search(t):
            classes.append("outcome")
        elif EP_SCALE.search(t):
            classes.append("scale")
        else:
            classes.append("unclassified")
    if "outcome" in classes:
        return "outcome"
    for c in ("scale", "surrogate"):
        if c in classes:
            return c
    return "unclassified"


# Oncology by condition text; the drug-development sense of "tumor" only.
ONC_COND = re.compile(
    r"cancer|carcinoma|tumor|tumour|leukemia|leukaemia|lymphoma|myeloma|melanoma|sarcoma"
    r"|glioma|glioblastoma|neoplasm|mesothelioma|myelodysplast", re.I)

# Oncology primary-endpoint families. OS must never match "...-free survival", and "OS" the
# abbreviation is matched case-sensitively so "per os" (by mouth) can't fire.
_ONC_FREE = re.compile(r"(progression|event|disease|recurrence|relapse|failure)[- ]free", re.I)
_ONC_OS_WORD = re.compile(r"overall survival", re.I)
_ONC_OS_ABBR = re.compile(r"\bOS\b")
_ONC_RR = re.compile(r"objective response|overall response|response rate|complete response"
                     r"|complete remission|\bORR\b", re.I)


def onc_endpoint(titles: list[str]) -> str:
    """OS / PFS-EFS / RR / other for one oncology trial, from its primary-outcome titles.
    Any (co-)primary OS makes it an OS trial — the trial must still wait for deaths."""
    for t in titles:
        if (_ONC_OS_WORD.search(t) or _ONC_OS_ABBR.search(t)) and not _ONC_FREE.search(t):
            return "OS"
    if any(_ONC_FREE.search(t) for t in titles):
        return "PFS/EFS"
    if any(_ONC_RR.search(t) for t in titles):
        return "RR"
    return "other"


# Cross-area surrogate-vs-outcome universes, by condition keywords. Each area names its
# canonical surrogate; the classifier is the same endpoint_class used everywhere.
AREA_CONDS = [
    ("Oncology", ONC_COND,
     "tumor response / PFS", "overall survival"),
    ("Diabetes", re.compile(r"diabetes", re.I),
     "HbA1c (blood sugar)", "cardiovascular events (CVOT)"),
    ("Cardiovascular", re.compile(
        r"hypertension|myocardial|coronary|heart failure|atrial fib|stroke|atheroscl"
        r"|dyslipid|hyperlipid|hypercholester|angina|thromboembol|cardiovascular", re.I),
     "blood pressure / LDL", "MACE (death, MI, stroke)"),
    ("Osteoporosis", re.compile(r"osteoporosis|bone loss|fracture", re.I),
     "bone mineral density", "fractures"),
    ("COPD / asthma", re.compile(r"copd|chronic obstructive|asthma", re.I),
     "FEV1 (lung function)", "exacerbations"),
    ("HIV", re.compile(r"\bhiv\b|human immunodeficiency", re.I),
     "viral load / CD4", "AIDS events, death"),
]


def demo() -> None:
    """Synthetic known-answer checks; any pattern change must keep these passing."""
    assert endpoint_class(["Change From Baseline in HbA1c at Week 24"]) == "surrogate"
    assert endpoint_class(["Change From Baseline in PANSS Total Score at Week 6"]) == "scale"
    assert endpoint_class(["Percentage of Participants Achieving ACR20 at Week 12"]) == "scale"
    assert endpoint_class(["Progression-free Survival", "Overall Survival"]) == "outcome", \
        "co-primary OS must dominate PFS"
    assert endpoint_class(["Progression-free Survival (PFS)"]) == "surrogate", \
        "PFS alone is a surrogate despite containing 'survival'"
    assert endpoint_class(["Time to First Occurrence of Composite of CV Death, MI, Stroke"]) \
        == "outcome"
    assert onc_endpoint(["Overall Survival"]) == "OS"
    assert onc_endpoint(["Progression-free Survival", "Overall Survival"]) == "OS"
    assert onc_endpoint(["Progression-Free Survival (PFS)"]) == "PFS/EFS"
    assert onc_endpoint(["Objective Response Rate"]) == "RR"
    assert onc_endpoint(["Percentage of Participants With Complete Remission"]) == "RR"
    print("endpoints OK")


if __name__ == "__main__":
    demo()
