from src.conversation.action import Action
from src.llm.output.actions_parser import actions_parser
from src.llm.output.output_parser import sentence_generation_settings
from src.llm.sentence_content import SentenceContent, SentenceTypeEnum


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
        ["equip", "wear", "put on"],
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
    parser = actions_parser(actions, "Camilla equip your armor")
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
        "arguments": {"item_name": "Iron Plate Armor"},
    }]
    assert parsed_equip.text == "Very well. I'll put this on."


def test_equip_category_isolates_exact_malformed_completion():
    actions = [make_inventory_action(), make_barter_action(), make_equip_action()]
    parser = actions_parser(actions, "Camilla equip your armor")
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
        "arguments": {"item_name": "Iron Plate Armor"},
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
        "arguments": {"item_name": "Iron Plate Armor"},
    }]


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
