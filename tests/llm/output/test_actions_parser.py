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


def parse_equip(text: str) -> SentenceContent:
    content = SentenceContent(None, text, SentenceTypeEnum.SPEECH)
    parser = actions_parser([make_equip_action()])
    parsed, _ = parser.modify_sentence_content(content, None, sentence_generation_settings(None))
    return parsed


def test_legacy_equip_carries_exact_item_name():
    parsed = parse_equip("Equip: mace | I can try that.")

    assert parsed.text == "I can try that."
    assert parsed.actions == [{
        "identifier": "mantella_npc_equip",
        "arguments": {"item_name": "mace"},
    }]


def test_legacy_equip_carries_generic_weapon_request():
    parsed = parse_equip("Equip: best weapon | I will choose one.")

    assert parsed.actions[0]["arguments"]["item_name"] == "best weapon"


def test_legacy_equip_without_argument_delimiter_keeps_fallback_behavior():
    parsed = parse_equip("Equip: I will get ready.")

    assert parsed.text == "I will get ready."
    assert parsed.actions == [{"identifier": "mantella_npc_equip"}]
