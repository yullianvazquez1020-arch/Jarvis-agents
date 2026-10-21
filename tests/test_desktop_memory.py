"""Desktop dialogue survives restart without replaying tools or crossing devices."""
from desktop_helpers import DesktopBase, ai_text, j
from unittest.mock import AsyncMock, patch

class DesktopMemory(DesktopBase):
    def test_restart_restores_plain_dialogue_for_same_device(self):
        token, device = self.pair()
        calls = self.ai(ai_text("Your project is Coral."), ai_text("Coral."))
        self.turn(token, "My project is named Coral", rid="memory-00001")
        saved = j.phase_a_restore("desk:" + device)
        self.assertEqual([x["role"] for x in saved], ["user", "assistant"])
        j.conversations.clear(); j._locks.clear()
        with patch.object(j, "run_tool", new=AsyncMock(side_effect=AssertionError("no replay"))):
            self.turn(token, "What is my project called?", rid="memory-00002")
        self.assertIn("Coral", str(calls[-1]["history"]))
        self.assertEqual(len(calls[-1]["history"]), 3)
        self.assertEqual(j.phase_a_restore("desk:another-device"), [])

    def test_other_device_does_not_receive_first_devices_dialogue(self):
        token, device = self.pair()
        other, _ = self.pair("Second screen device")
        calls = self.ai(ai_text("Noted."), ai_text("I don't know."))
        self.turn(token, "My project is named Coral", rid="memory-00001")
        j.conversations.clear(); j._locks.clear()
        self.turn(other, "What is my project called?", rid="memory-00002")
        self.assertEqual(len(calls[-1]["history"]), 1)
        self.assertNotIn("Coral", str(calls[-1]["history"]))

