from src.conversation.action import Action
from src.llm.output.actions_parser import actions_parser
from src.llm.output.output_parser import sentence_generation_settings
from src.llm.sentence_content import SentenceContent, SentenceTypeEnum
from types import SimpleNamespace
import pytest


def make_equip_action() -> Action:
    return Action(
        "mantella_npc_equip",
        "Equip",
        "Equip",
        "",
        "",
        True,
        False,
        True,
        True,
        False,
        "item_name",
        "npc_items",
        ["equip", "wear", "wearing", "put on"],
    )


def make_inventory_action() -> Action:
    return Action(
        "mantella_npc_inventory",
        "Inventory",
        "Inventory",
        "",
        "",
        True,
        False,
        True,
        True,
        False,
        "",
        "npc_items",
        ["check your inventory", "show your inventory"],
    )


def make_barter_action() -> Action:
    return Action(
        "mantella_npc_barter",
        "Barter",
        "Barter",
        "",
        "",
        False,
        False,
        True,
        True,
        False,
        "",
        "npc_items",
        ["barter", "lets trade", "trade with"],
    )


def parse_equip(text: str, actions: list[Action] | None = None) -> SentenceContent:
    content = SentenceContent(None, text, SentenceTypeEnum.SPEECH)
    parser = actions_parser(actions or [make_equip_action()])
    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))
    return parsed


def test_legacy_equip_carries_exact_item_name():
    parsed = parse_equip("Equip: Mace | I can try that.")

    assert parsed.text == "I can try that."
    assert parsed.actions == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "Mace"},
    }]


def test_legacy_equip_carries_multiword_item_name():
    parsed = parse_equip("Equip: Imperial Shield | Fine, I'll use it.")

    assert parsed.actions[0]["arguments"]["item_name"] == "Imperial Shield"
    assert parsed.text == "Fine, I'll use it."


def test_legacy_equip_carries_generic_weapon_request():
    parsed = parse_equip("Equip: best weapon | I will choose one.")

    assert parsed.actions[0]["arguments"]["item_name"] == "best weapon"


def test_legacy_equip_without_argument_delimiter_keeps_fallback_behavior():
    parsed = parse_equip("Equip: I will get ready.")

    assert parsed.text == "I will get ready."
    assert parsed.actions == [{"identifier": "mantella_npc_equip"}]


def test_legacy_equip_ignores_preceding_inventory_block():
    parsed = parse_equip(
        "Inventory: - Imperial Shield - Iron Armor Equip: Imperial Shield | Fine, I'll use it.",
        [make_inventory_action(), make_equip_action()],
    )

    assert parsed.actions[-1] == {
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "Imperial Shield"},
    }
    assert parsed.text == "Fine, I'll use it."


def test_legacy_equip_ignores_unrelated_text_before_prefix():
    parsed = parse_equip("Unexpected inventory text Imperial Mace Equip: Mace | Ready.")

    assert parsed.actions == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "Mace"},
    }]
    assert parsed.text == "Ready."


def test_legacy_equip_does_not_consume_following_action_block():
    parsed = parse_equip(
        "Equip: Imperial Shield Inventory: - Iron Armor | dialogue",
        [make_inventory_action(), make_equip_action()],
    )

    assert parsed.actions[-1] == {"identifier": "mantella_npc_equip"}


def test_equip_category_filters_inventory_and_barter_contamination():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    parser = actions_parser(actions, "Camilla equip your armor", {}, ["Camilla"])
    settings = sentence_generation_settings(None)

    inventory = SentenceContent(None, "Inventory: Belted Tunic Iron Plate Armor", SentenceTypeEnum.SPEECH)
    barter = SentenceContent(None, "Barter: I have some supplies.", SentenceTypeEnum.SPEECH)
    equip = SentenceContent(None, "Equip: Iron Plate Armor | Very well. I'll put this on.", SentenceTypeEnum.SPEECH)
    parsed_inventory, _ = parser.modify_sentence_content(inventory, None, settings)
    parsed_barter, _ = parser.modify_sentence_content(barter, None, settings)
    parsed_equip, _ = parser.modify_sentence_content(equip, None, settings)

    assert parsed_inventory.actions == []
    assert parsed_barter.actions == []
    assert parsed_equip.actions == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor"},
    }]
    assert parsed_equip.text == "Very well. I'll put this on."


def test_equip_category_isolates_exact_malformed_completion():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    parser = actions_parser(actions, "Camilla equip your armor", {}, ["Camilla"])
    content = SentenceContent(
        None,
        "Inventory: Belted Tunic Iron Plate Armor "
        "Inventory: Iron Shield "
        "Barter: I have some supplies. "
        "Equip: Iron Plate Armor | Very well. I'll put this on.",
        SentenceTypeEnum.SPEECH,
    )

    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))

    assert parsed.actions == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor"},
    }]
    assert parsed.text == "Very well. I'll put this on."


def test_inventory_noun_in_equip_request_is_not_an_inventory_category_hint():
    actions = [make_inventory_action(), make_equip_action()]
    parser = actions_parser(actions, "Equip the armor from your inventory")
    content = SentenceContent(
        None,
        "Inventory: Iron Plate Armor Equip: Iron Plate Armor | Very well.",
        SentenceTypeEnum.SPEECH,
    )

    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))

    assert parsed.actions == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor"},
    }]


def test_equipment_statement_filters_contaminated_inventory_action():
    actions = [make_inventory_action(), make_equip_action()]
    parser = actions_parser(actions, "You're wearing the armor right now")
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(None, "Inventory: I can open the inventory for you.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )

    assert parsed.actions == []


def test_inventory_category_filters_equip_and_barter_contamination():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    parser = actions_parser(actions, "Camilla, check your inventory")
    content = SentenceContent(
        None,
        "Barter: Inventory: Equip: Iron Shield | Here is what I have.",
        SentenceTypeEnum.SPEECH,
    )

    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))

    assert parsed.actions == [{"identifier": "mantella_npc_inventory"}]


def test_barter_category_filters_inventory_and_equip_contamination():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    parser = actions_parser(actions, "Camilla, let's trade")
    content = SentenceContent(
        None,
        "Inventory: Equip: Iron Shield | Barter: Let us see what I can sell.",
        SentenceTypeEnum.SPEECH,
    )

    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))

    assert parsed.actions == [{"identifier": "mantella_npc_barter"}]


def test_explicit_inventory_and_equip_categories_preserve_both_actions():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    parser = actions_parser(actions, "Check your inventory and equip the iron shield")
    content = SentenceContent(
        None,
        "Inventory: Barter: Equip: Iron Shield | Let us do this in order.",
        SentenceTypeEnum.SPEECH,
    )

    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))

    assert {action["identifier"] for action in parsed.actions} == {
        "mantella_npc_inventory",
        "mantella_npc_equip",
    }


def test_no_detected_category_preserves_existing_legacy_behavior():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    parser = actions_parser(actions, "Can you use a shield?")
    content = SentenceContent(
        None,
        "Inventory: Barter: Equip: Iron Shield | I can try.",
        SentenceTypeEnum.SPEECH,
    )

    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))

    assert {action["identifier"] for action in parsed.actions} == {
        "mantella_npc_inventory",
        "mantella_npc_barter",
        "mantella_npc_equip",
    }


def test_category_hint_is_not_treated_as_semantic_authorization():
    actions = [make_inventory_action(), make_equip_action()]
    for request in (
        "Do not equip the armor.",
        "Why did you equip that?",
        "Do you remember when I asked you to equip armor?",
    ):
        parser = actions_parser(actions, request)
        content = SentenceContent(
            None,
            "Inventory: Equip: Iron Plate Armor | I understand.",
            SentenceTypeEnum.SPEECH,
        )

        parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))

        assert parsed.actions == [{
            "identifier": "mantella_npc_equip",
            "arguments": {"item_name": "Iron Plate Armor"},
        }]


def test_action_result_generation_does_not_inherit_previous_player_category():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    player_turn_parser = actions_parser(actions, "Equip your armor")
    synthetic_followup_parser = actions_parser(actions, None)
    contaminated = SentenceContent(None, "Inventory: Barter:", SentenceTypeEnum.SPEECH)

    player_turn, _ = player_turn_parser.modify_sentence_content(
        SentenceContent(None, "Inventory: Barter:", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    synthetic_followup, _ = synthetic_followup_parser.modify_sentence_content(
        contaminated,
        None,
        sentence_generation_settings(None),
    )

    assert player_turn.actions == []
    assert {action["identifier"] for action in synthetic_followup.actions} == {
        "mantella_npc_inventory",
        "mantella_npc_barter",
    }


def test_retry_of_same_generation_retains_bound_category():
    parser = actions_parser(
        [make_inventory_action(), make_barter_action(), make_equip_action()],
        "Equip your armor",
    )

    for _ in range(2):
        parsed, _ = parser.modify_sentence_content(
            SentenceContent(None, "Inventory: Equip: best armor | All right.", SentenceTypeEnum.SPEECH),
            None,
            sentence_generation_settings(None),
        )
        assert [action["identifier"] for action in parsed.actions] == ["mantella_npc_equip"]


def test_interruption_uses_new_player_request_category():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    interrupted_parser = actions_parser(actions, "Equip your armor")
    replacement_parser = actions_parser(actions, "Check your inventory")

    old_turn, _ = interrupted_parser.modify_sentence_content(
        SentenceContent(None, "Inventory: Equip: best armor | Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    new_turn, _ = replacement_parser.modify_sentence_content(
        SentenceContent(None, "Inventory: Equip: best armor | Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )

    assert [action["identifier"] for action in old_turn.actions] == ["mantella_npc_equip"]
    assert [action["identifier"] for action in new_turn.actions] == ["mantella_npc_inventory"]


def test_unrestricted_legacy_action_keeps_existing_behavior():
    action = Action("wave", "Wave", "Wave", "", "", False, False, True, True, False)
    parser = actions_parser([action], "Tell me what happened earlier.")
    content = SentenceContent(None, "Wave: Hello.", SentenceTypeEnum.SPEECH)

    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))

    assert parsed.actions == [{"identifier": "wave"}]


def missing_required_equip(request: str, response: str = "I cannot equip that.") -> list[dict]:
    parser = actions_parser([make_equip_action()], request)
    parser.modify_sentence_content(
        SentenceContent(None, response, SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    missing, _ = parser.get_missing_required_actions()
    return missing


def test_explicit_generic_equip_omission_requires_runtime_evaluation():
    for request in (
        "Please equip your armor",
        "I'm telling you to equip your armor.",
        "Please put on your armor.",
    ):
        assert missing_required_equip(request) == [{
            "identifier": "mantella_npc_equip",
            "arguments": {"item_name": "best armor"},
        }]


def test_explicit_correction_requires_equip_again():
    assert missing_required_equip("You do not have the shield equipped. Equip the shield.") == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "shield"},
    }]


@pytest.mark.parametrize("player_text", (
    "Camilla, wear your armor.",
    "Camilla, equip your armor.",
    "Put on your iron boots.",
    "Draw your sword.",
    "Ready your weapon.",
    "You didn't put the boots on.",
    "You're not actually wearing the armor.",
    "That didn't equip; try again.",
    "No, I meant the iron armor.",
    "Put those boots back on.",
))
def test_clear_equip_requests_create_obligations(player_text):
    assert missing_required_equip(player_text)


@pytest.mark.parametrize("player_text", (
    "Good job wearing your armor.",
    "Camilla good job on continuing to wear your armor.",
    "I see you're wearing your armor.",
    "You're still wearing the boots.",
    "Camilla looks good in armor.",
    "What are you wearing?",
    "Is Camilla wearing armor?",
    "Uthgerd, what is Camilla wearing?",
    "I like that armor you're wearing.",
    "You have been wearing that all day.",
    "Keep telling me about your armor.",
))
def test_equipment_observations_do_not_create_equip_obligations(player_text):
    assert missing_required_equip(player_text) == []


def test_repeated_current_request_creates_independent_obligation():
    first = missing_required_equip("Equip the shield.")
    second = missing_required_equip("Equip the shield.")
    assert first == second
    assert first[0]["arguments"]["item_name"] == "shield"


def test_mentions_capability_questions_and_negation_do_not_require_equip():
    for request in (
        "That shield looks useful.",
        "Can you use a shield?",
        "What armor are you wearing?",
        "Do not equip the shield.",
    ):
        assert missing_required_equip(request) == []


def test_request_phrased_as_question_requires_equip():
    assert missing_required_equip("Can you equip the shield?")[0]["arguments"] == {"item_name": "shield"}


def test_history_and_events_cannot_create_current_turn_obligation():
    assert missing_required_equip("Where did you get that shield?") == []
    assert missing_required_equip("How are you feeling?", "Camilla equipped Imperial Shield.") == []
    parser = actions_parser([make_equip_action()], None)
    parser.modify_sentence_content(
        SentenceContent(None, "Equip the shield happened earlier.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert parser.get_missing_required_actions()[0] == []


def test_inventory_action_does_not_satisfy_explicit_equip_obligation():
    parser = actions_parser(
        [make_inventory_action(), make_equip_action()],
        "Check your inventory and equip the armor.",
    )
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(None, "Inventory: Here is what I have.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert parsed.actions == [{"identifier": "mantella_npc_inventory"}]
    assert parser.get_missing_required_actions()[0] == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor"},
    }]


def test_emitted_legacy_or_structured_equip_satisfies_obligation():
    legacy = actions_parser([make_equip_action()], "Equip your armor.")
    legacy.modify_sentence_content(
        SentenceContent(None, "Equip: best armor | All right.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert legacy.get_missing_required_actions()[0] == []

    structured = actions_parser([make_equip_action()], "Equip your armor.")
    structured.mark_actions_triggered([{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor"},
    }])
    assert structured.get_missing_required_actions()[0] == []


def test_generic_weapon_and_specific_item_targets_are_preserved():
    assert missing_required_equip("Use your best weapon.")[0]["arguments"] == {"item_name": "best weapon"}
    assert missing_required_equip("Could you equip the Iron Shield?")[0]["arguments"] == {"item_name": "Iron Shield"}


def test_generic_armor_requests_override_currently_worn_clothing_output():
    for request in (
        "Equip your armor.",
        "Equip the armor.",
        "Put on your armor.",
        "Wear your armor.",
        "Wear some armor.",
    ):
        parser = actions_parser([make_equip_action()], request)
        parsed, _ = parser.modify_sentence_content(
            SentenceContent(None, "Equip: Belted Tunic | All right.", SentenceTypeEnum.SPEECH),
            None,
            sentence_generation_settings(None),
        )
        assert parsed.actions == [{
            "identifier": "mantella_npc_equip",
            "arguments": {"item_name": "best armor"},
        }]
        assert parser.get_missing_required_actions()[0] == []


def test_generic_weapon_request_overrides_prompt_inferred_weapon():
    for request in ("Equip your weapon.", "Draw your weapon.", "Ready a weapon."):
        parser = actions_parser([make_equip_action()], request)
        parsed, _ = parser.modify_sentence_content(
            SentenceContent(None, "Equip: Iron Dagger | Ready.", SentenceTypeEnum.SPEECH),
            None,
            sentence_generation_settings(None),
        )
        assert parsed.actions[0]["arguments"] == {"item_name": "best weapon"}


def test_named_item_request_remains_exact():
    for request, expected in (
        ("Equip Iron Armor.", "Iron Armor"),
        ("Equip the Imperial Shield.", "Imperial Shield"),
    ):
        parser = actions_parser([make_equip_action()], request)
        parsed, _ = parser.modify_sentence_content(
            SentenceContent(None, "Equip: Belted Tunic | Fine.", SentenceTypeEnum.SPEECH),
            None,
            sentence_generation_settings(None),
        )
        assert parsed.actions[0]["arguments"] == {"item_name": expected}


def test_structured_equip_uses_bound_target_and_preserves_source():
    parser = actions_parser([make_equip_action()], "Camilla, equip your armor.", {}, ["Camilla"])
    structured = {
        "identifier": "mantella_npc_equip",
        "arguments": {"source": "Camilla Valerius", "item_name": "Belted Tunic"},
    }
    reconciled = parser.mark_actions_triggered([structured])

    assert reconciled == [structured]
    assert structured["arguments"] == {
        "source": "Camilla Valerius",
        "item_name": "best armor",
    }
    assert parser.get_missing_required_actions()[0] == []


def test_multinpc_fallback_keeps_addressed_actor_when_model_speaker_changes():
    parser = actions_parser(
        [make_equip_action()],
        "Camilla equip your armor now",
        {},
        ["Camilla Valerius", "Uthgerd the Unbroken"],
    )
    parser.modify_sentence_content(
        SentenceContent(SimpleNamespace(name="Uthgerd the Unbroken"), "I already did.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )

    assert parser.get_missing_required_actions()[0] == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor", "source": "Camilla Valerius"},
    }]


def test_multinpc_obligations_keep_distinct_addressed_actors():
    parser = actions_parser(
        [make_equip_action()],
        "Camilla, equip your armor. Uthgerd, equip your weapon.",
        {},
        ["Camilla Valerius", "Uthgerd the Unbroken"],
    )

    missing = parser.get_missing_required_actions()[0]
    assert missing == [
        {
            "identifier": "mantella_npc_equip",
            "arguments": {"item_name": "best armor", "source": "Camilla Valerius"},
        },
        {
            "identifier": "mantella_npc_equip",
            "arguments": {"item_name": "best weapon", "source": "Uthgerd the Unbroken"},
        },
    ]


def test_multinpc_emitted_action_cannot_replace_bound_actor():
    parser = actions_parser(
        [make_equip_action()],
        "Camilla, equip your armor.",
        {},
        ["Camilla Valerius", "Uthgerd the Unbroken"],
    )
    structured = {
        "identifier": "mantella_npc_equip",
        "arguments": {"source": "Uthgerd the Unbroken", "item_name": "Iron Armor"},
    }

    assert parser.mark_actions_triggered([structured]) == []
    assert parser.get_missing_required_actions()[0] == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor", "source": "Camilla Valerius"},
    }]


def test_inventory_and_generic_equip_preserve_both_with_runtime_target():
    parser = actions_parser(
        [make_inventory_action(), make_equip_action()],
        "Check your inventory and equip your armor.",
    )
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(
            None,
            "Inventory: Equip: Belted Tunic | Here is what I have.",
            SentenceTypeEnum.SPEECH,
        ),
        None,
        sentence_generation_settings(None),
    )

    assert parsed.actions == [
        {"identifier": "mantella_npc_inventory"},
        {
            "identifier": "mantella_npc_equip",
            "arguments": {"item_name": "best armor"},
        },
    ]


def test_referential_request_keeps_concrete_same_generation_resolution():
    parser = actions_parser([make_equip_action()], "Yes, please equip it.")
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(None, "Equip: Imperial Shield | I suppose you are right.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )

    assert parsed.actions == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "Imperial Shield"},
    }]
    assert parser.get_missing_required_actions()[0] == []


def test_unresolved_referential_request_does_not_guess_or_dispatch():
    parser = actions_parser([make_equip_action()], "Equip it.")
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(None, "Equip: it | All right.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )

    assert parsed.actions == []
    assert parser.get_missing_required_actions()[0] == []


def test_referential_structured_equip_preserves_source_and_concrete_resolution():
    parser = actions_parser([make_equip_action()], "Camilla, put that on.", {}, ["Camilla"])
    structured = {
        "identifier": "mantella_npc_equip",
        "arguments": {"source": "Camilla Valerius", "item_name": "Imperial Shield"},
    }

    reconciled = parser.mark_actions_triggered([structured])

    assert reconciled == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"source": "Camilla Valerius", "item_name": "Imperial Shield"},
    }]


def test_negated_separable_put_on_does_not_authorize_equip():
    assert missing_required_equip("Do not put that on.") == []


def test_separable_put_on_requires_a_concrete_same_generation_resolution():
    parser = actions_parser([make_equip_action()], "Put that on.")
    unresolved = {
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "that"},
    }

    assert parser.mark_actions_triggered([unresolved]) == []


def test_referential_resolution_requires_current_request_authorization():
    parser = actions_parser([make_equip_action()], None)
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(None, "Imperial Shield was equipped earlier.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )

    assert parsed.actions == []
    assert parser.get_missing_required_actions()[0] == []


def test_same_turn_explicit_antecedent_resolves_pronoun_for_emitted_and_fallback_actions():
    request = "No, it's just regular iron armor, please check and equip it."
    speaker = SimpleNamespace(name="Camilla")

    emitted_parser = actions_parser([make_equip_action()], request, {})
    emitted, _ = emitted_parser.modify_sentence_content(
        SentenceContent(speaker, "Equip: it | Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert emitted.actions[0]["arguments"] == {"item_name": "regular iron armor"}

    fallback_parser = actions_parser([make_equip_action()], request, {})
    fallback_parser.modify_sentence_content(
        SentenceContent(speaker, "Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert fallback_parser.get_missing_required_actions()[0] == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "regular iron armor"},
    }]


def test_inventory_antecedent_resolves_same_turn_pronoun():
    parser = actions_parser(
        [make_equip_action()],
        "The shield is in your inventory, equip it.",
        {},
    )
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(SimpleNamespace(name="Camilla"), "Equip: it | Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert parsed.actions[0]["arguments"] == {"item_name": "shield"}


def test_player_explicit_target_resolves_immediate_followup_for_same_npc():
    targets = {}
    speaker = SimpleNamespace(name="Camilla")
    first = actions_parser([make_equip_action()], "Equip regular iron armor.", targets)
    first.modify_sentence_content(
        SentenceContent(speaker, "Equip: Iron Armor | Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert targets == {"camilla": "regular iron armor"}

    followup = actions_parser(
        [make_equip_action()],
        "No, you're still not wearing it. Please equip it now.",
        targets,
    )
    followup.modify_sentence_content(
        SentenceContent(speaker, "I already did.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert followup.get_missing_required_actions()[0] == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "regular iron armor"},
    }]


def test_player_equip_target_memory_isolated_by_npc():
    targets = {"npc a": "Iron Armor"}
    parser = actions_parser(
        [make_equip_action()],
        "NPC B, equip it now.",
        targets,
        ["NPC A", "NPC B"],
    )
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(SimpleNamespace(name="NPC B"), "Equip: it | Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )

    assert parsed.actions == []
    assert parser.get_missing_required_actions()[0] == []
    assert targets == {"npc a": "Iron Armor"}


def test_equip_vocatives_are_removed_before_target_extraction():
    cases = (
        ("Please equip your armor, Camilia.", "best armor"),
        ("Camilla, equip your armor.", "best armor"),
        ("Equip the iron armor, Camilla.", "iron armor"),
        ("Camilla equip the Imperial Shield.", "Imperial Shield"),
    )
    for request, expected in cases:
        parser = actions_parser(
            [make_equip_action()],
            request,
            {},
            ["Camilla Valerius"],
        )
        parser.modify_sentence_content(
            SentenceContent(SimpleNamespace(name="Camilla Valerius"), "I will do that.", SentenceTypeEnum.SPEECH),
            None,
            sentence_generation_settings(None),
        )

        assert parser.get_missing_required_actions()[0] == [{
            "identifier": "mantella_npc_equip",
            "arguments": {"item_name": expected},
        }]


def test_actor_contaminated_target_is_never_remembered():
    targets = {}
    parser = actions_parser(
        [make_equip_action()],
        "Please equip your armor, Camilia.",
        targets,
        ["Camilla Valerius"],
    )
    parser.modify_sentence_content(
        SentenceContent(SimpleNamespace(name="Camilla Valerius"), "Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    parser.get_missing_required_actions()

    assert targets == {"camilla valerius": "best armor"}
    assert all("camilia" not in value.lower() for value in targets.values())


def test_malformed_previous_target_cannot_leak_into_correction():
    targets = {"camilla valerius": "armor, Camilia"}
    parser = actions_parser(
        [make_equip_action()],
        "Camilla, equip it again.",
        targets,
        ["Camilla Valerius"],
    )
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(SimpleNamespace(name="Camilla Valerius"), "Equip: it | Fine.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )

    assert parsed.actions == []
    assert parser.get_missing_required_actions()[0] == []
    assert targets == {}


@pytest.mark.parametrize("command_text", (
    "Camilla, equip your armor.",
    "Camilla where is your armor put it back on equip your armor",
    "Can you please equip your armor?",
    "Please put your armor back on.",
    "You don't have your armor on. Put it back on.",
))
def test_natural_language_armor_commands_create_one_generic_obligation(command_text):
    assert missing_required_equip(command_text) == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor"},
    }]


def test_shield_residue_is_normalized_to_category_target():
    assert missing_required_equip("Please equip your shield, too.") == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "shield"},
    }]


def test_chest_qualifier_is_not_sent_as_part_of_item_name():
    assert missing_required_equip("Please put on the iron armor for your chest.") == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "iron armor"},
    }]


def test_compound_inventory_and_equip_create_ordered_obligations():
    parser = actions_parser(
        [make_inventory_action(), make_equip_action()],
        "Check your inventory and then equip the iron armor.",
    )
    missing, _ = parser.get_missing_required_actions()
    assert missing == [
        {"identifier": "mantella_npc_inventory", "arguments": {}},
        {"identifier": "mantella_npc_equip", "arguments": {"item_name": "iron armor"}},
    ]


@pytest.mark.parametrize("player_request", (
    "Give me more lore on your family.",
    "Give me your opinion.",
    "Give me an explanation.",
    "Give me some advice.",
    "Give me more details.",
    "Give me your thoughts.",
    "Give me a reason.",
    "Tell me about your family.",
))
def test_conversational_give_phrases_do_not_create_inventory_obligations(player_request):
    parser = actions_parser([make_inventory_action()], player_request)
    assert parser.get_missing_required_actions()[0] == []


@pytest.mark.parametrize("player_request", (
    "Give me your sword.",
    "Give me the potion.",
    "Give me 100 gold.",
    "Show me your inventory.",
    "Let me see what you're carrying.",
    "I want to give you this shield.",
    "Take this armor from me.",
    "Trade items with me.",
))
def test_item_transfer_and_explicit_inventory_requests_create_inventory_obligations(player_request):
    parser = actions_parser([make_inventory_action()], player_request)
    assert parser.get_missing_required_actions()[0] == [{
        "identifier": "mantella_npc_inventory",
        "arguments": {},
    }]


def test_unrelated_model_argument_cannot_replace_compound_explicit_target():
    parser = actions_parser([make_equip_action()], "Please equip the iron armor for your chest.")
    parsed, _ = parser.modify_sentence_content(
        SentenceContent(None, "Equip: Belted Tunic | I will do that.", SentenceTypeEnum.SPEECH),
        None,
        sentence_generation_settings(None),
    )
    assert parsed.actions[0]["arguments"] == {"item_name": "iron armor"}


def test_unresolved_compound_pronoun_does_not_create_duplicate_when_concrete_equip_follows():
    parser = actions_parser([make_equip_action()], "Put it back on and equip your armor.")
    missing, _ = parser.get_missing_required_actions()
    assert missing == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "best armor"},
    }]
