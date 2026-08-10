from src.llm.output.output_parser import output_parser, sentence_generation_settings
from src.llm.sentence_content import SentenceContent
from src.conversation.action import Action
import src.utils as utils
import re

logger = utils.get_logger()

    
class actions_parser(output_parser):
    def __init__(self, actions: list[Action], current_player_request: str | None = None) -> None:
        super().__init__()
        self.__actions = actions
        self.__detected_actions_by_group = self.__detect_action_categories(current_player_request)
        self.__required_actions = self.__detect_required_actions(current_player_request)
        self.__triggered_action_identifiers: set[str] = set()
        self.__obligation_speaker = None

    def cut_sentence(self, output: str, current_settings: sentence_generation_settings) -> tuple[SentenceContent|None, str|None]:
        return None, output

    def modify_sentence_content(self, cut_content: SentenceContent, last_content: SentenceContent | None, settings: sentence_generation_settings) -> tuple[SentenceContent | None, SentenceContent | None]:
        if self.__obligation_speaker is None:
            self.__obligation_speaker = cut_content.speaker
        action_source = cut_content.text
        if ":" in action_source:
            for action in self.__actions:
                keyword = action.keyword + ":"
                if keyword in action_source:
                    if self.__is_cross_action_contamination(action):
                        logger.warning(f"Ignoring cross-action contamination: {action.name} ({action.identifier})")
                        continue
                    action_text = self.__get_action_text(action_source, keyword)
                    cut_content.text = cut_content.text.replace(keyword,"").strip()
                    parsed_action = {'identifier': action.identifier}
                    if action.legacy_argument:
                        argument_value, separator, remaining_text = action_text.partition("|")
                        argument_value = argument_value.strip()
                        if separator and argument_value:
                            parsed_action['arguments'] = {action.legacy_argument: argument_value}
                            cut_content.text = remaining_text.strip()
                    cut_content.actions.append(parsed_action)
                    self.mark_actions_triggered([parsed_action])
                    logger.log(28, f'Action triggered: {action.name} ({action.identifier}), arguments={parsed_action.get("arguments", {})}')
                    if action.is_interrupting:
                        settings.stop_generation = True
        return cut_content, last_content

    def mark_actions_triggered(self, actions: list[dict]) -> None:
        """Record legacy or structured actions already emitted in this generation."""
        self.__triggered_action_identifiers.update(
            action.get('identifier', '') for action in actions if isinstance(action, dict)
        )

    def get_missing_required_actions(self) -> tuple[list[dict], object | None]:
        """Return unfulfilled explicit current-turn obligations and their response speaker."""
        missing = [
            action for identifier, action in self.__required_actions.items()
            if identifier not in self.__triggered_action_identifiers
        ]
        return missing, self.__obligation_speaker

    def __detect_required_actions(self, current_player_request: str | None) -> dict[str, dict]:
        """Detect only high-confidence Equip requests from this exact player turn.

        This is deliberately narrower than semantic intent classification. The LLM
        remains responsible for ambiguous language; this closes only clear command
        forms so an all-dialogue response cannot silently skip runtime evaluation.
        """
        if not current_player_request:
            return {}
        equip_action = next(
            (action for action in self.__actions if action.identifier == 'mantella_npc_equip'),
            None,
        )
        if not equip_action:
            return {}

        request = utils.remove_extra_whitespace(current_player_request).strip()
        # Negation applies only when it directly governs the requested action. This
        # does not reject corrections such as "You do not have it equipped. Equip it."
        if re.search(r"\b(?:do not|don't|dont|never)\s+(?:please\s+)?(?:equip|wear|wield|draw|ready|put\s+on|use\s+(?:your\s+)?best)\b", request, re.IGNORECASE):
            return {}

        boundary = r"(?:^|[.!?]\s*|,\s*|\band\s+)"
        lead = r"(?:please\s+|(?:can|could|would|will)\s+you\s+(?:please\s+)?|(?:i am|i'm|im)\s+telling\s+you\s+to\s+)?"
        patterns = (
            boundary + lead + r"(?:equip|wear|wield|draw|ready)\s+(?P<target>[^.!?]+)",
            boundary + lead + r"put\s+on\s+(?P<target>[^.!?]+)",
            boundary + lead + r"use\s+(?P<target>(?:your\s+)?best\s+(?:armor|armour|weapon))\b",
        )
        match = next((candidate for pattern in patterns if (candidate := re.search(pattern, request, re.IGNORECASE))), None)
        if not match:
            return {}

        target = self.__normalize_equip_target(match.group('target'))
        if not target:
            return {}
        return {
            equip_action.identifier: {
                'identifier': equip_action.identifier,
                'arguments': {equip_action.legacy_argument: target},
            }
        }

    def __normalize_equip_target(self, target: str) -> str:
        target = re.sub(r"\s+(?:from|in)\s+(?:your|the)\s+inventory\s*$", "", target, flags=re.IGNORECASE)
        target = re.sub(r"\s+(?:for me|please)\s*$", "", target, flags=re.IGNORECASE)
        target = re.sub(r"^(?:your|the|a|an)\s+", "", target.strip(" ,"), flags=re.IGNORECASE)
        normalized = utils.clean_text(target)
        if normalized in {'armor', 'armour', 'best armor', 'best armour', 'clothing', 'clothes', 'gear', 'best clothing'}:
            return 'best armor'
        if normalized in {'weapon', 'best weapon'}:
            return 'best weapon'
        return target.strip()

    def __detect_action_categories(self, current_player_request: str | None) -> dict[str, set[str]]:
        """Find clear action-category hints without deciding semantic intent.

        These hints only isolate protected legacy action families from one another.
        The LLM and action prompt remain responsible for negation, tense, history,
        hypotheticals, and whether an action should be invoked at all.
        """
        if current_player_request is None:
            return {}
        normalized_request = f" {utils.clean_text(current_player_request)} "
        detected: dict[str, set[str]] = {}
        for action in self.__actions:
            if not action.legacy_action_group:
                continue
            if any(
                normalized_hint and f" {normalized_hint} " in normalized_request
                for hint in action.legacy_action_hints
                if (normalized_hint := utils.clean_text(hint))
            ):
                detected.setdefault(action.legacy_action_group, set()).add(action.identifier)
        return detected

    def __is_cross_action_contamination(self, action: Action) -> bool:
        if not action.legacy_action_group:
            return False
        detected_actions = self.__detected_actions_by_group.get(action.legacy_action_group, set())
        return bool(detected_actions) and action.identifier not in detected_actions

    def __get_action_text(self, text: str, keyword: str) -> str:
        """Return only the text belonging to the specified action prefix."""
        action_start = text.find(keyword) + len(keyword)
        action_end = len(text)
        for action in self.__actions:
            next_keyword = action.keyword + ":"
            next_action = text.find(next_keyword, action_start)
            if next_action >= 0 and next_action < action_end:
                action_end = next_action
        return text[action_start:action_end].strip()
    
    def get_cut_indicators(self) -> list[str]:
        return [":"]
