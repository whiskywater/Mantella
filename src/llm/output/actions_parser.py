from src.llm.output.output_parser import output_parser, sentence_generation_settings
from src.llm.sentence_content import SentenceContent
from src.conversation.action import Action
import src.utils as utils

logger = utils.get_logger()

    
class actions_parser(output_parser):
    def __init__(self, actions: list[Action]) -> None:
        super().__init__()
        self.__actions = actions

    def cut_sentence(self, output: str, current_settings: sentence_generation_settings) -> tuple[SentenceContent|None, str|None]:
        return None, output

    def modify_sentence_content(self, cut_content: SentenceContent, last_content: SentenceContent | None, settings: sentence_generation_settings) -> tuple[SentenceContent | None, SentenceContent | None]:
        action_source = cut_content.text
        if ":" in action_source:
            for action in self.__actions:
                keyword = action.keyword + ":"
                if keyword in action_source:
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
