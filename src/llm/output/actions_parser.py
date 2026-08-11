from src.llm.output.output_parser import output_parser, sentence_generation_settings
from src.llm.sentence_content import SentenceContent
from src.conversation.action import Action
import src.utils as utils
import re

logger = utils.get_logger()

    
class actions_parser(output_parser):
    def __init__(self, actions: list[Action], current_player_request: str | None = None, player_equip_targets: dict[str, str] | None = None, participant_names: list[str] | None = None) -> None:
        super().__init__()
        self.__actions = actions
        self.__participant_names = participant_names or []
        self.__player_equip_targets = player_equip_targets if player_equip_targets is not None else {}
        self.__requested_actor_name, self.__addressed_actor_phrase = self.__find_addressed_actor(current_player_request, self.__participant_names)
        self.__detected_actions_by_group = self.__detect_action_categories(current_player_request)
        # Obligations are ordered occurrences, not a set keyed only by action
        # identifier.  This preserves compound requests such as Inventory +
        # Equip (and repeated requests) without allowing one action to satisfy
        # another occurrence.
        self.__required_actions = self.__detect_required_actions(current_player_request)
        self.__triggered_required_indexes: set[int] = set()
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
                    parsed_actions = self.mark_actions_triggered([parsed_action], cut_content.speaker)
                    if not parsed_actions:
                        logger.warning(f"Ignoring unresolved referential action target: {action.name} ({action.identifier})")
                        continue
                    parsed_action = parsed_actions[0]
                    cut_content.actions.append(parsed_action)
                    logger.log(28, f'Action triggered: {action.name} ({action.identifier}), arguments={parsed_action.get("arguments", {})}')
                    if action.is_interrupting:
                        settings.stop_generation = True
        return cut_content, last_content

    def mark_actions_triggered(self, actions: list[dict], speaker=None) -> list[dict]:
        """Align and record legacy or structured actions emitted in this generation.

        A high-confidence Equip request from the bound player turn is authoritative
        for its target. This prevents the model from replacing a generic inventory
        request such as "your armor" with currently worn prompt context, while
        preserving unrelated arguments such as the selected NPC source.
        """
        reconciled_actions = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            identifier = action.get('identifier', '')
            action_source = action.get('arguments', {}).get('source', '')
            if action_source and any(
                required.get('identifier') == identifier
                and required.get('arguments', {}).get('source', '')
                and utils.clean_text(required['arguments']['source']) != utils.clean_text(action_source)
                for required in self.__required_actions
            ):
                # A model action explicitly routed to another participant must
                # not survive as an unrelated action when this turn has a
                # source-bound obligation.
                continue
            required_index, required_action = self.__find_required_action(action, speaker)
            if required_action and required_action.get('arguments'):
                required_target = required_action['arguments'].get('item_name', '')
                emitted_target = action.get('arguments', {}).get('item_name', '')
                actor_key = self.__get_actor_key(action, speaker)
                resolved_target = self.__resolve_required_target(required_target, emitted_target, actor_key)
                if not resolved_target:
                    continue
                action.setdefault('arguments', {})['item_name'] = resolved_target
                required_source = required_action.get('arguments', {}).get('source', '')
                if required_source:
                    # The current player turn, not the model's sentence
                    # speaker, owns the actor route for this obligation.
                    action['arguments']['source'] = required_source
                self.__remember_explicit_player_target(required_target, resolved_target, actor_key)
            if required_index is not None:
                self.__triggered_required_indexes.add(required_index)
            reconciled_actions.append(action)
        return reconciled_actions

    def get_missing_required_actions(self) -> tuple[list[dict], object | None]:
        """Return unfulfilled explicit current-turn obligations and their response speaker."""
        missing = []
        for index, action in enumerate(self.__required_actions):
            if index in self.__triggered_required_indexes:
                continue
            required_target = action.get('arguments', {}).get('item_name', '')
            actor_key = self.__get_actor_key(action, self.__obligation_speaker)
            if action.get('identifier') == 'mantella_npc_equip':
                resolved_target = self.__resolve_required_target(required_target, '', actor_key)
                if not resolved_target:
                    continue
            else:
                resolved_target = required_target
            resolved_action = {
                'identifier': action.get('identifier', ''),
                'arguments': dict(action.get('arguments', {})),
            }
            if action.get('identifier') == 'mantella_npc_equip':
                resolved_action['arguments']['item_name'] = resolved_target
            self.__remember_explicit_player_target(required_target, resolved_target, actor_key)
            missing.append(resolved_action)
        return missing, self.__obligation_speaker

    def __find_required_action(self, action: dict, speaker) -> tuple[int | None, dict | None]:
        identifier = action.get('identifier', '')
        for index, required in enumerate(self.__required_actions):
            if index in self.__triggered_required_indexes or required.get('identifier') != identifier:
                continue
            required_source = required.get('arguments', {}).get('source', '')
            action_source = action.get('arguments', {}).get('source', '')
            if required_source and action_source and utils.clean_text(required_source) != utils.clean_text(action_source):
                continue
            return index, required
        return None, None

    def __get_actor_key(self, action: dict, speaker) -> str:
        source = action.get('arguments', {}).get('source', '')
        if isinstance(source, str) and source.strip():
            return utils.clean_text(source)
        if self.__requested_actor_name:
            return utils.clean_text(self.__requested_actor_name)
        speaker_name = getattr(speaker, 'name', '') if speaker is not None else ''
        return utils.clean_text(speaker_name)

    def __resolve_required_target(self, required_target: str, emitted_target: str, actor_key: str) -> str:
        if not self.__is_referential_equip_target(required_target):
            return required_target if self.__is_safe_equip_target(required_target) else ''
        previous_target = self.__player_equip_targets.get(actor_key, '') if actor_key else ''
        if previous_target and self.__is_safe_equip_target(previous_target):
            return previous_target
        if previous_target and actor_key:
            self.__player_equip_targets.pop(actor_key, None)
        if emitted_target and self.__is_safe_equip_target(emitted_target):
            return emitted_target
        return ''

    def __remember_explicit_player_target(self, required_target: str, resolved_target: str, actor_key: str) -> None:
        if actor_key and required_target and not self.__is_referential_equip_target(required_target) and self.__is_safe_equip_target(resolved_target):
            self.__player_equip_targets[actor_key] = resolved_target

    def __is_referential_equip_target(self, target: str) -> bool:
        return utils.clean_text(target) in {'it', 'that', 'this', 'one', 'the one'}

    def __is_safe_equip_target(self, target: str) -> bool:
        """Reject unresolved command residue and participant-contaminated targets.

        This validation also protects the conversation-scoped correction map from
        values produced by an older/malformed generation.
        """
        normalized = utils.clean_text(target)
        if not normalized or self.__is_referential_equip_target(target):
            return False
        if normalized.split()[-1:] in (['now'], ['again'], ['please']):
            return False
        actor_aliases = [
            alias
            for name in self.__participant_names
            for alias in self.__actor_aliases(name)
        ]
        if any(self.__actor_name_matches(normalized, alias) for alias in actor_aliases):
            return False
        if ',' in target:
            suffix = target.rsplit(',', 1)[1].strip(" .!?")
            if any(self.__actor_name_matches(suffix, alias) for alias in actor_aliases):
                return False
        return True

    def __detect_required_actions(self, current_player_request: str | None) -> list[dict]:
        """Extract ordered obligations from this exact player turn.

        This is intentionally a small command extractor, not an English intent
        classifier.  It recognizes action verbs and their noun phrase targets,
        while leaving ambiguous discussion to the model.  Crucially, each
        occurrence becomes its own obligation, so Inventory cannot satisfy a
        following Equip in the same request.
        """
        if not current_player_request:
            return []
        raw_request = utils.remove_extra_whitespace(current_player_request).strip()
        request = self.__strip_addressed_actor(raw_request)
        obligations: list[tuple[int, dict]] = []

        equip_action = next((action for action in self.__actions if action.identifier == 'mantella_npc_equip'), None)
        if equip_action:
            equip_pattern = re.compile(r"\b(?:equip|wear|wearing|wield|draw|ready)\b|\bmeant\b(?=\s+(?:the|your|an?|some)\s+)|\buse\s+(?=(?:your\s+)?best\s+(?:armor|armour|weapon)\b)|\bput\s+on\b|\bput\b(?=\s+[^.!?]{1,80}\s+on\b)", re.IGNORECASE)
            raw_matches = list(equip_pattern.finditer(raw_request))
            for occurrence, match in enumerate(equip_pattern.finditer(request)):
                if self.__is_non_command_equip(request, match):
                    continue
                target = self.__extract_equip_target(request, match)
                if not target:
                    continue
                source = self.__obligation_source(
                    raw_request,
                    raw_matches[occurrence].start() if occurrence < len(raw_matches) else match.start(),
                )
                arguments = {equip_action.legacy_argument: target}
                # In a multi-NPC turn the generated sentence speaker is not an
                # actor-routing signal. Preserve the addressed actor on each
                # obligation so fallback and emitted actions use the same target.
                if source and len(self.__participant_names) > 1:
                    arguments['source'] = source
                obligations.append((match.start(), {
                    'identifier': equip_action.identifier,
                    'arguments': arguments,
                }))

        inventory_action = next((action for action in self.__actions if action.identifier == 'mantella_npc_inventory'), None)
        if inventory_action and self.__has_inventory_request(request):
            obligations.append((self.__action_phrase_position(request, ('inventory', 'give', 'take')), {
                'identifier': inventory_action.identifier,
                'arguments': {},
            }))

        barter_action = next((action for action in self.__actions if action.identifier == 'mantella_npc_barter'), None)
        if barter_action and re.search(r"\b(?:barter|trade|buy|sell)\b", request, re.IGNORECASE):
            obligations.append((self.__action_phrase_position(request, ('barter', 'trade', 'buy', 'sell')), {
                'identifier': barter_action.identifier,
                'arguments': {},
            }))

        obligations.sort(key=lambda item: item[0])
        # A malformed compound correction may contain an unresolved "put it on"
        # fragment immediately before a concrete Equip command.  The concrete
        # command is the actionable obligation; retaining both would cause a
        # duplicate fallback or let the model's argument satisfy the wrong one.
        concrete_equip = any(
            action.get('identifier') == 'mantella_npc_equip'
            and not self.__is_referential_equip_target(action.get('arguments', {}).get('item_name', ''))
            for _, action in obligations
        )
        if concrete_equip:
            obligations = [
                item for item in obligations
                if item[1].get('identifier') != 'mantella_npc_equip'
                or not self.__is_referential_equip_target(item[1].get('arguments', {}).get('item_name', ''))
            ]
        deduped: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for _, action in obligations:
            key = (action.get('identifier', ''), action.get('arguments', {}).get('item_name', ''))
            if key not in seen:
                deduped.append(action)
                seen.add(key)
        return deduped

    def __action_phrase_position(self, request: str, phrases: tuple[str, ...]) -> int:
        positions = [request.lower().find(phrase) for phrase in phrases if request.lower().find(phrase) >= 0]
        return min(positions) if positions else len(request)

    def __obligation_source(self, request: str, action_position: int) -> str:
        """Return the participant explicitly addressed for this action clause."""
        if not self.__participant_names:
            return ''
        latest_start = -1
        latest_name = ''
        prefix = request[:action_position]
        for name in self.__participant_names:
            for alias in self.__actor_aliases(name):
                match = re.search(
                    r"(?:^|[.!?,])\s*" + re.escape(alias) + r"(?:\s*,|\s+)",
                    prefix,
                    re.IGNORECASE,
                )
                if match and match.start() >= latest_start:
                    latest_start = match.start()
                    latest_name = name
        return latest_name or self.__requested_actor_name

    def __has_inventory_request(self, request: str) -> bool:
        return bool(re.search(
            r"\b(?:check|show|open|look\s+at|view)\s+(?:your\s+)?inventory\b|"
            r"\b(?:give\s+me|give\s+you|take\s+from)\b",
            request,
            re.IGNORECASE,
        ))

    def __is_non_command_equip(self, request: str, match: re.Match) -> bool:
        before = request[max(0, match.start() - 48):match.start()].lower()
        verb = match.group(0).lower()
        # Direct negation is not a request.  Corrections remain valid because the
        # corrective verb is in a later clause after the negated statement.
        if re.search(r"(?:do not|don't|dont|never)\s+(?:please\s+)?$", before):
            return True
        if re.search(r"(?:^|[.!?]\s*)(?:why did|what did|when did|do you remember when)\b", request[:match.start()], re.IGNORECASE):
            return True
        # A state/praise clause can contain the imperative verb as a trailing
        # infinitive ("good job on continuing to wear ..."). It is not a new
        # request. Keep genuine requests such as "I want you to wear ..."
        # eligible by limiting this guard to praise/continuation/history cues.
        if re.search(r"(?:good job|nice job|continue|continuing|keep|you said|remember)\s+(?:on\s+)?(?:continuing\s+)?to\s*$", before):
            return True
        if verb == 'wearing':
            # Bare state descriptions and questions are not commands. A
            # negated state is a correction request and remains actionable.
            if re.search(r"\b(?:not|isn't|aren't|wasn't|weren't)\s+(?:actually\s+)?$", before):
                return False
            if re.search(r"(?:good job|nice job|still|already|have been|you're|you are|what are you|what is|is [^.!?]+|looks good|like that armor)\s*$", before):
                return True
        if verb in {'wear'} and re.search(r"\bwhat\s+armor\s+are\s+you\s+$", before):
            return True
        return False

    def __extract_equip_target(self, request: str, match: re.Match) -> str:
        start = match.end()
        # Stop at the next explicit clause/action boundary, not merely at a
        # comma: item names may contain commas, while "shield, too" is residue.
        boundary = re.search(
            r"(?:\s+(?:and\s+then|then|and)\s+|\s+(?:equip|wear|wield|draw|ready|put|check|open|show)\b|[.!?])",
            request[start:],
            re.IGNORECASE,
        )
        end = start + boundary.start() if boundary else len(request)
        target = request[start:end].strip(" ,")
        if target.lower().startswith('on '):
            target = target[3:]
        target = self.__normalize_equip_target(target)
        if self.__is_referential_equip_target(target):
            resolved = self.__resolve_same_request_referent(request, target)
            target = resolved
        if self.__is_referential_equip_target(target):
            return target
        return target if self.__is_safe_equip_target(target) else ''

    def __normalize_equip_target(self, target: str) -> str:
        target = re.sub(r"\s+(?:from|in)\s+(?:your|the)\s+inventory\s*$", "", target, flags=re.IGNORECASE)
        target = re.sub(r"\s+(?:(?:right\s+)?now|again|for me|please|too|also|back)\s*$", "", target, flags=re.IGNORECASE)
        target = re.sub(r"\s+on\s*$", "", target, flags=re.IGNORECASE)
        target = re.sub(r"\s+(?:back|again|now|please|too|also)\s*$", "", target, flags=re.IGNORECASE)
        target = re.sub(r"\s+for\s+(?:your|the)\s+(?:chest|head|feet|hands|body|left hand|right hand)\s*$", "", target, flags=re.IGNORECASE)
        target = re.sub(r"^(?:your|the|a|an|some)\s+", "", target.strip(" ,"), flags=re.IGNORECASE)
        normalized = utils.clean_text(target)
        if normalized in {'armor', 'armour', 'best armor', 'best armour', 'clothing', 'clothes', 'gear', 'best clothing'}:
            return 'best armor'
        if normalized in {'weapon', 'best weapon'}:
            return 'best weapon'
        return target.strip()

    def __resolve_same_request_referent(self, request: str, referential_target: str) -> str:
        command = r"(?:please\s+)?(?:check(?:\s+your\s+inventory)?\s+and\s+)?(?:equip|wear|wield|draw|ready|put\s+on)"
        patterns = (
            r"\b(?:it\s+is|it's)\s+(?:just\s+)?(?P<item>[^,.!?]+?)\s*,\s*" + command + r"\s+(?:it|that|this|one)\b",
            r"(?P<item>\b(?:the|this|that|your|an?|some)\s+[^,.!?]+?)\s+is\s+(?:in|inside)\s+your\s+inventory[^,.!?]*,\s*" + command + r"\s+(?:it|that|this|one)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, request, re.IGNORECASE)
            if match:
                candidate = self.__normalize_equip_target(match.group('item'))
                if self.__looks_like_equipment(candidate):
                    return candidate
        prior_text = request[: request.lower().rfind(referential_target.lower())]
        if re.search(r"\b(?:armor|armour|clothing|gear)\b", prior_text, re.IGNORECASE):
            return 'best armor'
        if re.search(r"\b(?:shield|weapon|sword|mace|axe|bow|dagger)\b", prior_text, re.IGNORECASE):
            return 'best weapon' if re.search(r"\bweapon\b", prior_text, re.IGNORECASE) else 'shield'
        return referential_target

    def __looks_like_equipment(self, target: str) -> bool:
        equipment_words = {
            'armor', 'armour', 'shield', 'weapon', 'sword', 'mace', 'axe', 'bow',
            'dagger', 'helmet', 'helm', 'boots', 'gauntlets', 'clothing', 'clothes', 'gear',
        }
        return any(word in equipment_words for word in utils.clean_text(target).split())

    def __find_addressed_actor(self, current_player_request: str | None, participant_names: list[str]) -> tuple[str, str]:
        if not current_player_request:
            return '', ''
        request = current_player_request.strip()
        for name in sorted(participant_names, key=len, reverse=True):
            for alias in self.__actor_aliases(name):
                exact_prefix = re.match(r"^(?P<actor>" + re.escape(alias) + r")(?:\s*,\s*|\s+)", request, re.IGNORECASE)
                if exact_prefix:
                    return name, exact_prefix.group('actor')
                exact_suffix = re.search(r",\s*(?P<actor>" + re.escape(alias) + r")\s*[.!?]*$", request, re.IGNORECASE)
                if exact_suffix:
                    return name, exact_suffix.group('actor')

        # Speech recognition commonly drops or doubles one letter in a vocative.
        # Fuzzy matching is limited to a comma-delimited suffix or the first word,
        # and only against participant names, so item names are never guessed.
        candidates: list[str] = []
        suffix = re.search(r",\s*(?P<actor>[A-Za-z][A-Za-z'\-]*)\s*[.!?]*$", request)
        if suffix:
            candidates.append(suffix.group('actor'))
        prefix = re.match(r"^(?P<actor>[A-Za-z][A-Za-z'\-]*)(?:\s*,\s*|\s+)", request)
        if prefix:
            candidates.append(prefix.group('actor'))
        for candidate in candidates:
            for name in participant_names:
                if any(self.__actor_name_matches(candidate, alias) for alias in self.__actor_aliases(name)):
                    return name, candidate
        return '', ''

    def __strip_addressed_actor(self, request: str) -> str:
        if not self.__addressed_actor_phrase:
            return request
        request = re.sub(
            r"^" + re.escape(self.__addressed_actor_phrase) + r"(?:\s*,\s*|\s+)",
            "",
            request,
            count=1,
            flags=re.IGNORECASE,
        )
        return re.sub(
            r",\s*" + re.escape(self.__addressed_actor_phrase) + r"\s*([.!?]*)$",
            r"\1",
            request,
            count=1,
            flags=re.IGNORECASE,
        )

    def __actor_aliases(self, participant_name: str) -> list[str]:
        aliases = [participant_name.strip()]
        first_name = participant_name.strip().split()[0] if participant_name.strip() else ''
        first_name_is_unique = sum(
            1
            for name in self.__participant_names
            if name.strip() and utils.clean_text(name.strip().split()[0]) == utils.clean_text(first_name)
        ) == 1
        if first_name and first_name_is_unique and utils.clean_text(first_name) != utils.clean_text(participant_name):
            aliases.append(first_name)
        return aliases

    def __actor_name_matches(self, candidate: str, participant_alias: str) -> bool:
        left = utils.clean_text(candidate)
        right = utils.clean_text(participant_alias)
        if not left or not right:
            return False
        if left == right:
            return True
        if abs(len(left) - len(right)) > 1:
            return False
        previous = list(range(len(right) + 1))
        for row, left_char in enumerate(left, start=1):
            current = [row]
            for column, right_char in enumerate(right, start=1):
                current.append(min(
                    current[column - 1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                ))
            previous = current
        return previous[-1] <= 1

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
