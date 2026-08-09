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
