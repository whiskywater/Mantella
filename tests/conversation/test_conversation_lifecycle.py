from unittest.mock import MagicMock

from src.conversation.conversation import Conversation


def _ended_conversation_stub() -> Conversation:
    conversation = Conversation.__new__(Conversation)
    conversation._Conversation__has_already_ended = False
    conversation._Conversation__stop_generation = MagicMock()
    conversation._Conversation__sentences = MagicMock()
    conversation._Conversation__save_conversation = MagicMock()
    return conversation


def test_end_detaches_once_and_starts_background_persistence():
    conversation = _ended_conversation_stub()

    conversation.end()
    conversation.end()

    assert conversation._Conversation__save_conversation.call_count == 1
    conversation._Conversation__save_conversation.assert_called_once_with(
        is_reload=False,
        end_timestamp=None,
        background=True,
    )
    assert conversation._Conversation__stop_generation.call_count == 1


class _SnapshotCharacters:
    def __init__(self):
        self.pending_shares = [("A", "B", "ref-b")]

    def get_pending_shares(self):
        return list(self.pending_shares)

    def clear_pending_shares(self):
        self.pending_shares.clear()

    def get_non_player_characters(self):
        return []

    def get_all_characters_since_start(self):
        return []


def test_background_save_uses_detached_snapshot_and_clears_only_old_shares(monkeypatch):
    conversation = Conversation.__new__(Conversation)
    config = MagicMock(conversation_summary_enabled=True)
    characters = _SnapshotCharacters()
    context = MagicMock(config=config, world_id="conversation-a", game_days=12.5)
    context.npcs_in_conversation = characters
    conversation._Conversation__context = context
    conversation._Conversation__messages = MagicMock()
    conversation._Conversation__messages.get_talk_only.return_value = []
    conversation._Conversation__conversation_type = MagicMock()
    conversation._Conversation__rememberer = MagicMock()

    queued = {}

    class ImmediateThread:
        def __init__(self, target, args, daemon):
            queued["target"] = target
            queued["args"] = args
            queued["daemon"] = daemon

        def start(self):
            queued["started"] = True

    monkeypatch.setattr("src.conversation.conversation.Thread", ImmediateThread)
    conversation._Conversation__save_conversation(
        is_reload=False,
        end_timestamp=None,
        background=True,
    )

    assert queued["started"] is True
    assert queued["daemon"] is True
    assert characters.pending_shares == []
    # Execute the detached job after the live conversation would be replaced.
    queued["target"](*queued["args"])
    conversation._Conversation__rememberer.save_conversation_state.assert_called_once()
    args = conversation._Conversation__rememberer.save_conversation_state.call_args.args
    assert args[3] == "conversation-a"
    assert args[5] == [("A", "B", "ref-b")]


def test_participant_removal_uses_detached_persistence(monkeypatch):
    conversation = Conversation.__new__(Conversation)
    conversation._Conversation__messages = MagicMock()
    conversation._Conversation__messages.__len__.return_value = 4
    removed = object()
    context = MagicMock()
    context.add_or_update_characters.return_value = [removed]
    conversation._Conversation__context = context
    conversation._Conversation__save_conversation = MagicMock()

    conversation.add_or_update_character([])

    conversation._Conversation__save_conversation.assert_called_once_with(
        is_reload=True,
        departed_npcs=[removed],
        background=True,
    )
