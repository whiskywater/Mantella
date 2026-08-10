from src.llm.output.output_parser import output_parser, sentence_generation_settings
from src.llm.sentence_content import SentenceContent
from src.conversation.action import Action
import src.utils as utils

logger = utils.get_logger()

    
class actions_parser(output_parser):
    def __init__(self, actions: list[Action], current_player_request: str | None = None) -> None:
        super().__init__()
        self.__actions = actions
        self.__detected_actions_by_group = self.__detect_action_categories(current_player_request)

    def cut_sentence(self, output: str, current_settings: sentence_generation_settings) -> tuple[SentenceContent|None, str|None]:
        return None, output

    def modify_sentence_content(self, cut_content: SentenceContent, last_content: SentenceContent | None, settings: sentence_generation_settings) -> tuple[SentenceContent | None, SentenceContent | None]:
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
                    logger.log(28, f'Action triggered: {action.name} ({action.identifier}), arguments={parsed_action.get("arguments", {})}')
                    if action.is_interrupting:
                        settings.stop_generation = True
        return cut_content, last_content

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
