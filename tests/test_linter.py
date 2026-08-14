"""The pedagogy linter — §9.2, §9.3, §9.4, §9.6.

Every fixture below was MEASURED before its assertion was written (week 3 shipped
two prose fixtures that asserted the wrong thing because they were assumed). The
measured values are in the comments so a later reader can tell whether a fixture
has drifted rather than whether a rule has broken.

For each rule: one scene that fires it, one that does not.
"""
from __future__ import annotations

import pytest

from explainer import linter as L

# MEASURED: 25 narration words, so §9.4's 20% allowance is 5 on-screen words.
NARR = ("Two transactions each read the same two rows. Each one checks the rule "
        "and finds it satisfied. Then each updates a different row and commits.")
NARR_WORDS = 25
ALLOWANCE = 5


def scene(ref="s01", slots=None, template="labelled_diagram", cues=1,
          seconds=60, new_terms=(), narration=NARR, safe_bottom=0.15,
          slot_name="present"):
    return L.SceneView(
        ref=ref, gagne_slot=slot_name, narration_text=narration,
        visual_spec={"template": template,
                     "slots": slots if slots is not None
                     else {"nodes": [{"id": "t1", "label": "T1"},
                                     {"id": "t2", "label": "T2"}],
                           "focus": "t1"},
                     "cues": [{}] * cues,
                     "captionSafeArea": {"bottom": safe_bottom}},
        pedagogy_meta={"duration_target_seconds": seconds,
                       "new_terms": list(new_terms)})


def rules(findings):
    return {f.rule for f in findings}


# --------------------------------------------- the clean baseline

def test_a_clean_scene_fires_no_scene_level_rule():
    """MEASURED: 2 on-screen words, 3 objects, 1 cue, 60s, 1 text element."""
    s = scene()
    assert L.on_screen_word_count(s.slots) == 2
    assert L.text_element_count(s.slots) == 2
    assert not L.scene_findings(s, has_preceding_vocab=False)


def test_a_clean_video_fires_nothing():
    """The one that matters most — a linter that flags everything is a linter
    nobody reads. MEASURED: four scenes, four templates, 240s total, inside
    §9.2's 180-300 band, no template over the authored 40% share.

    It has to be a real video: `video_outside_target_band` and
    `template_variety` measure a VIDEO, so a single 60s scene fires both by
    construction and proves nothing about whether the rules are quiet on good
    work."""
    scenes = [
        scene("s01", template="cold_open", cues=0,
              slots={"premise": "two doctors on call"}),
        scene("s02", template="labelled_diagram", cues=2),
        scene("s03", template="term_card", cues=1,
              slots={"term": "write skew",
                     "characteristic": "disjoint writes"}),
        scene("s04", template="key_phrase", cues=0,
              slots={"phrase": "both commit"}),
    ]
    assert sum(s.seconds for s in scenes) == 240
    report = L.lint(scenes)
    assert not report.findings, report.render()
    assert report.ok


# ------------------------------------------------ §9.4 the priority rule

def test_onscreen_text_over_twenty_percent_fires():
    """MEASURED: 18 on-screen words against 25 narrated = 72%, over §9.4's 20%."""
    s = scene(slots={"nodes": [
        {"id": "a", "label": "each transaction reads the same two rows and checks"},
        {"id": "b", "label": "then updates a different row and commits the change"}]})
    assert L.on_screen_word_count(s.slots) == 18
    found = L.check_onscreen_text_share(s)
    assert len(found) == 1
    f = found[0]
    assert f.rule == "onscreen_text_share" and f.severity == "warning"
    assert f.measured["onscreen_words"] == 18
    assert f.measured["narration_words"] == NARR_WORDS
    assert f.threshold["max_words"] == ALLOWANCE


def test_onscreen_text_at_the_allowance_does_not_fire():
    """MEASURED: 5 words == the allowance. The boundary is inclusive."""
    s = scene(slots={"nodes": [{"id": "a", "label": "same rows read"},
                               {"id": "b", "label": "disjoint writes"}]})
    assert L.on_screen_word_count(s.slots) == ALLOWANCE
    assert not L.check_onscreen_text_share(s)


def test_a_verbatim_narration_sentence_on_screen_is_blocking():
    """§9.4's evidence: identical full text scores BELOW no text at all
    (.25 vs .33 recall). It renders fine, so nothing else would catch it."""
    s = scene(template="key_phrase",
              slots={"phrase": "Then each updates a different row and commits."})
    found = L.check_verbatim_onscreen(s)
    assert len(found) == 1
    assert found[0].severity == "blocking"
    assert found[0].rule == "verbatim_narration_onscreen"


def test_a_near_paraphrase_is_not_flagged_as_verbatim():
    """The §9.4 sweet spot: near-change scored .40/.49, the best condition."""
    s = scene(template="key_phrase",
              slots={"phrase": "each writes a different row"})
    assert not L.check_verbatim_onscreen(s)


def test_verbatim_matching_ignores_case_and_punctuation():
    s = scene(template="key_phrase",
              slots={"phrase": "THEN EACH UPDATES A DIFFERENT ROW AND COMMITS"})
    assert L.check_verbatim_onscreen(s)


# ------------------------------------------------------ §9.3 load rules

def test_more_than_four_text_bearing_objects_fires():
    """MEASURED: 8 objects, carrying text, against §9.3's 4."""
    s = scene(slots={"rows": [f"row {i}" for i in range(6)],
                     "columns": ["a", "b"]}, template="table_build")
    n, has_text = L.count_objects(s.slots)
    assert (n, has_text) == (8, True)
    found = L.check_object_count(s)
    assert found and found[0].threshold["max_objects"] == 4


def test_seven_objects_without_text_does_not_fire():
    """§9.3 allows 7 when none carry text."""
    s = scene(slots={"nodes": [{"id": f"n{i}"} for i in range(7)]})
    n, has_text = L.count_objects(s.slots)
    assert (n, has_text) == (7, False)
    assert not L.check_object_count(s)


def test_text_density_over_thirty_words_fires():
    """MEASURED: 35 on-screen words against §9.3's 30."""
    s = scene(slots={"rows": [f"a fairly wordy row label number {i} here"
                              for i in range(5)]}, template="table_build")
    assert L.on_screen_word_count(s.slots) == 35
    assert "onscreen_text_density" in rules(L.check_text_density(s))


def test_more_than_three_text_elements_fires():
    s = scene(slots={"rows": ["a", "b", "c", "d"]}, template="table_build")
    assert "onscreen_text_elements" in rules(L.check_text_density(s))


def test_three_text_elements_does_not_fire():
    s = scene(slots={"rows": ["a", "b", "c"]}, template="table_build")
    assert "onscreen_text_elements" not in rules(L.check_text_density(s))


def test_more_than_four_new_interacting_elements_fires():
    """§9.3's ≤4. Approximated from new_terms + edges, and the finding says so."""
    s = scene(new_terms=["xmin", "xmax", "snapshot"],
              slots={"nodes": [{"id": "a"}],
                     "edges": [{"from": "a", "to": "a"}, {"from": "a", "to": "a"}]})
    found = L.check_new_interacting_elements(s)
    assert found and found[0].measured["approximation"] == "new_terms + edges"


def test_four_new_interacting_elements_does_not_fire():
    s = scene(new_terms=["xmin", "xmax"],
              slots={"nodes": [{"id": "a"}],
                     "edges": [{"from": "a", "to": "a"}, {"from": "a", "to": "a"}]})
    assert not L.check_new_interacting_elements(s)


# ------------------------------------------------------ §9.2 rules

def test_three_new_terms_without_a_vocabulary_scene_fires():
    """§9.2 Pre-training triggers at 3."""
    s = scene(new_terms=["xmin", "xmax", "snapshot"])
    found = L.check_pretraining(s, has_preceding_vocab=False)
    assert found and found[0].threshold["trigger"] == 3


def test_three_new_terms_with_a_preceding_vocabulary_scene_does_not_fire():
    s = scene(new_terms=["xmin", "xmax", "snapshot"])
    assert not L.check_pretraining(s, has_preceding_vocab=True)


def test_a_term_card_earlier_in_the_video_satisfies_pretraining():
    vocab = scene("s01", template="term_card",
                  slots={"term": "xmin", "characteristic": "the creating xid"})
    heavy = scene("s02", new_terms=["xmin", "xmax", "snapshot"])
    assert "pretraining_missing" not in rules(L.lint([vocab, heavy]).findings)
    assert "pretraining_missing" in rules(L.lint([heavy]).findings)


def test_a_scene_with_no_visual_spec_is_blocking():
    s = L.SceneView(ref="s01", gagne_slot="present", narration_text=NARR,
                    visual_spec={}, pedagogy_meta={})
    found = L.check_multimedia(s)
    assert found and found[0].severity == "blocking"


def test_a_static_title_held_past_eight_seconds_fires():
    s = scene(template="title_card", seconds=12,
              slots={"title": "what you'll do"})
    assert "static_title_too_long" in rules(L.check_multimedia(s))


def test_a_static_title_within_eight_seconds_does_not_fire():
    s = scene(template="title_card", seconds=8, slots={"title": "what you'll do"})
    assert not L.check_multimedia(s)


def test_zero_cues_on_a_signalling_template_fires():
    s = scene(cues=0)
    found = L.check_cue_count(s)
    assert found and found[0].threshold == {"min": 1, "max": 3}


def test_zero_cues_on_a_non_signalling_template_does_not_fire():
    """ISSUE-5's exemption, visible here so a change to it breaks a test."""
    s = scene(template="key_phrase", cues=0, slots={"phrase": "frozen"})
    assert not L.check_cue_count(s)


def test_an_unknown_template_in_a_stored_spec_is_blocking():
    s = scene(template="RemotionThing")
    found = L.check_cue_count(s)
    assert found and found[0].severity == "blocking"


def test_a_reduced_caption_safe_area_is_blocking():
    """§16.2 + CHALLENGES: the safe area is not the model's to set."""
    s = scene(safe_bottom=0.05)
    found = L.check_caption_safe_area(s)
    assert found and found[0].severity == "blocking"
    assert found[0].threshold["required_bottom"] == 0.15


def test_the_template_safe_area_passes():
    assert not L.check_caption_safe_area(scene(safe_bottom=0.15))


# ------------------------------------------------------- video-level

def test_a_video_over_the_six_minute_cap_is_blocking():
    scenes = [scene(f"s{i:02d}", seconds=60) for i in range(7)]      # 420s
    found = [f for f in L.check_video_duration(scenes)
             if f.rule == "video_over_hard_cap"]
    assert found and found[0].severity == "blocking"
    assert found[0].threshold["hard_cap"] == 360


def test_a_video_inside_the_target_band_does_not_fire():
    scenes = [scene(f"s{i:02d}", seconds=60) for i in range(4)]      # 240s
    assert not [f for f in L.check_video_duration(scenes)
                if f.rule.startswith("video_")]


def test_a_scene_longer_than_the_segment_boundary_fires():
    found = L.check_video_duration([scene(seconds=150)])
    assert "segment_too_long" in rules(found)


def test_a_dominant_template_fires_with_the_threshold_marked_authored():
    """ISSUE-4: v0.2 has no variety budget. The number is printed in the
    finding so it can be argued with rather than mistaken for spec."""
    scenes = ([scene(f"s{i:02d}", template="table_build") for i in range(4)]
              + [scene("s05", template="key_phrase", slots={"phrase": "x"})])
    found = L.check_template_variety(scenes)
    assert found
    f = found[0]
    assert f.severity == "warning"
    assert f.threshold["authored"] is True
    assert f.threshold["spec_source"] is None
    assert "AUTHORED AND UNREVIEWED" in f.message
    assert f.measured["distribution"] == {"table_build": 4, "key_phrase": 1}


def test_an_even_template_spread_does_not_fire():
    scenes = [scene("s01", template="labelled_diagram"),
              scene("s02", template="table_build"),
              scene("s03", template="series_build")]
    assert not L.check_template_variety(scenes)


# ------------------------------------------- unspecified and unimplemented

@pytest.mark.parametrize("fn,args", [
    (L.check_nonnative_text_allowance, (0.5,)),
    (L.check_term_density_allowance, ([],)),
])
def test_rules_needing_a_number_the_spec_lacks_raise(fn, args):
    """Same discipline as the Gagné caps: raise rather than invent."""
    with pytest.raises(L.UnspecifiedThreshold) as e:
        fn(*args)
    assert "§9.4" in str(e.value)


def test_the_report_names_what_it_did_not_check():
    """'No finding' must be distinguishable from 'not implemented' — §9.2's
    coherence score is the one most tempting to fake with string matching."""
    report = L.lint([scene()])
    assert "coherence_relevance_score" in report.not_implemented
    assert "onscreen_semantic_similarity" in report.not_implemented
    assert "temporal_contiguity" in report.not_implemented
    assert "NOT CHECKED" in report.render()


def test_no_model_based_rule_is_secretly_implemented():
    for rule in L.MODEL_BASED_RULES:
        assert not hasattr(L, f"check_{rule}"), \
            f"{rule} is model-based per §9.6 and must not be approximated here"


# ------------------------------------------------------------- report

def test_blocking_findings_make_the_report_not_ok():
    """§6 Stage 3: scenes that fail hard checks do not render."""
    s = scene(safe_bottom=0.05)
    report = L.lint([s])
    assert not report.ok
    assert s.ref in report.blocking_scenes()
    assert report.render().startswith("BLOCKING")


def test_every_finding_carries_measured_threshold_and_fix():
    """§4.3 makes the report customer-visible; an unpopulated row is broken."""
    scenes = [scene("s01", safe_bottom=0.05, cues=0,
                    slots={"rows": [f"a wordy label number {i} here"
                                    for i in range(6)]}, template="table_build",
                    seconds=150)]
    report = L.lint(scenes)
    assert report.findings
    for f in report.findings:
        assert f.measured, f"{f.rule} has no measurement"
        assert f.threshold, f"{f.rule} has no threshold"
        assert f.fix, f"{f.rule} has no fix"
