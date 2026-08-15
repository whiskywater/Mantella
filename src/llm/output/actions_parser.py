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
        # A model may emit an action-only response such as ``Inventory:``
        # without a following sentence terminator. Surface the prefix as a
        # normal SentenceContent so the shared authorization gate handles it
        # identically to an action followed by dialogue.
        stripped = output.lstrip()
        leading = output[:len(output) - len(stripped)]
        for action in self.__actions:
            prefix = action.keyword + ":"
            if stripped.startswith(prefix):
                # The sentence accumulator treats ':' as a cut indicator, so
                # an Equip response can arrive first as just ``Equip:`` and
                # the item name in the following stream chunk.  Do not emit
                # an argument-less Equip invocation at that boundary; retain
                # the prefix until the item payload is available.  When the
                # payload is already present, keep the complete sentence so
                # modify_sentence_content can preserve arguments.item.
                if action.identifier == "mantella_npc_equip":
                    payload = stripped[len(prefix):].strip()
                    if not payload:
                        return None, output
                    return SentenceContent(
                        current_settings.current_speaker,
                        output,
                        current_settings.sentence_type,
                        False,
                    ), ""
                end = len(leading) + len(prefix)
                return SentenceContent(current_settings.current_speaker, output[:end], current_settings.sentence_type, False), output[end:]
        return None, output

    def modify_sentence_content(self, cut_content: SentenceContent, last_content: SentenceContent | None, settings: sentence_generation_settings) -> tuple[SentenceContent | None, SentenceContent | None]:
        if ":" in cut_content.text:
            for action in self.__actions:
                keyword = action.keyword + ":"
                if keyword in cut_content.text:
                    action_text = cut_content.text.split(keyword, 1)[1].strip()
                    cut_content.text = cut_content.text.replace(keyword,"").strip()
                    invocation = {'identifier': action.identifier}
                    if action.identifier == 'mantella_npc_equip' and action_text:
                        invocation['arguments'] = {'item': action_text.split('|', 1)[0].strip()}
                    cut_content.actions.append(invocation)
                    logger.log(28, f'Action triggered: {action.name} ({action.identifier})')
                    if action.is_interrupting:
                        settings.stop_generation = True
        return cut_content, last_content

    def parse_corrective_response(self, output: str, settings: sentence_generation_settings) -> list[dict]:
        """Parse only action prefixes at real line/response boundaries for a bounded retry."""
        invocations: list[dict] = []
        for raw_line in output.replace("\r\n", "\n").split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            # A multi-NPC correction may retain the exact speaker label. The
            # retry is already bound to one stable actor by its lifecycle.
            if ":" in line:
                possible_speaker, remainder = line.split(":", 1)
                if not any(line.startswith(action.keyword + ":") for action in self.__actions) and ":" in remainder:
                    line = remainder.strip()
            for action in self.__actions:
                prefix = action.keyword + ":"
                if not line.startswith(prefix):
                    continue
                action_text = line[len(prefix):].strip()
                invocation = {"identifier": action.identifier}
                if action.identifier == "mantella_npc_equip" and action_text:
                    invocation["arguments"] = {"item": action_text.split("|", 1)[0].strip()}
                invocations.append(invocation)
                break
        return invocations
    
    def get_cut_indicators(self) -> list[str]:
        return [":"]
