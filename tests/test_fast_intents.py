from __future__ import annotations

import unittest

from jarvis_assistant.agent.fast_intents import match_fast_intent


class FastIntentTests(unittest.TestCase):
    def test_open_youtube_uses_browser_without_llm(self) -> None:
        decision = match_fast_intent("open youtube")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.status, "tool_call")
        self.assertEqual(decision.tool_calls[0].tool, "control_browser")
        self.assertIn("youtube.com", decision.tool_calls[0].arguments["action"]["url"])

    def test_common_search_phrase_uses_web_search(self) -> None:
        decision = match_fast_intent("search for python logging")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "web_search")
        self.assertEqual(decision.tool_calls[0].arguments["query"], "python logging")

    def test_list_files_uses_safe_shell_command(self) -> None:
        decision = match_fast_intent("list files")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "run_shell_command")
        self.assertEqual(decision.tool_calls[0].arguments["command"], "dir")

    def test_common_small_talk_stays_local(self) -> None:
        decision = match_fast_intent("tell me something")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.status, "final")
        self.assertIn("online", decision.message.lower())

    def test_open_app_and_type_uses_single_tool(self) -> None:
        decision = match_fast_intent('open notepad and type "abc"')

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.status, "tool_call")
        self.assertEqual(len(decision.tool_calls), 1)
        self.assertEqual(decision.tool_calls[0].tool, "open_application_and_type")
        self.assertEqual(decision.tool_calls[0].arguments["app_name"], "notepad")
        self.assertEqual(decision.tool_calls[0].arguments["text"], "abc")

    def test_open_app_and_type_trims_voice_tail(self) -> None:
        decision = match_fast_intent("open notepad and type abc in that")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "open_application_and_type")
        self.assertEqual(decision.tool_calls[0].arguments["text"], "abc")

    def test_open_app_and_type_is_not_notepad_specific(self) -> None:
        decision = match_fast_intent("open chrome and type hello world")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "open_application_and_type")
        self.assertEqual(decision.tool_calls[0].arguments["app_name"], "chrome")
        self.assertEqual(decision.tool_calls[0].arguments["text"], "hello world")

    def test_hinglish_open_app_and_type(self) -> None:
        decision = match_fast_intent("notepad kholo aur type abc")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "open_application_and_type")
        self.assertEqual(decision.tool_calls[0].arguments["app_name"], "notepad")
        self.assertEqual(decision.tool_calls[0].arguments["text"], "abc")

    def test_hinglish_system_status(self) -> None:
        decision = match_fast_intent("battery batao")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "get_system_info")

    def test_hinglish_time_replies_in_hinglish(self) -> None:
        decision = match_fast_intent("time batao")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.status, "final")
        self.assertIn("Abhi", decision.message)
        self.assertIn("hai", decision.message)

    def test_common_time_phrase_stays_local(self) -> None:
        decision = match_fast_intent("what is the time right now")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.status, "final")
        self.assertIn("It is", decision.message)

    def test_english_small_talk_stays_english(self) -> None:
        decision = match_fast_intent("tell me something")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.status, "final")
        self.assertIn("I am online", decision.message)

    def test_play_uses_youtube_media_search(self) -> None:
        decision = match_fast_intent("play arijit singh")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "control_browser")
        self.assertIn("youtube.com/results", decision.tool_calls[0].arguments["action"]["url"])
        self.assertIn("arijit+singh", decision.tool_calls[0].arguments["action"]["url"])

    def test_hinglish_play_uses_youtube_media_search(self) -> None:
        decision = match_fast_intent("arijit singh chalao")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "control_browser")
        self.assertIn("arijit+singh", decision.tool_calls[0].arguments["action"]["url"])

    def test_hinglish_known_app_chalao_opens_app(self) -> None:
        decision = match_fast_intent("chrome chalao")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.tool_calls[0].tool, "open_application")
        self.assertEqual(decision.tool_calls[0].arguments["app_name"], "chrome")


if __name__ == "__main__":
    unittest.main()
