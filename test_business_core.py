"""Safety and accounting regression checks for business_core; stdlib only."""
import tempfile
import unittest
from pathlib import Path
from business_core import BusinessCore

class TestBusinessCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = BusinessCore(Path(self.tmp.name) / "business.sqlite3")

    def tearDown(self):
        self.core.close()
        self.tmp.cleanup()

    def test_tenant_isolation_and_approval(self):
        c = self.core.add_contact("ISLAFIX", "Client", phone="7870000000")
        with self.assertRaises(ValueError):
            self.core.add_ticket("AIBA", "Wrong tenant", contact_id=c)
        self.core.add_ticket("ISLAFIX", "Repair request", channel="phone", contact_id=c)
        pending = self.core.propose_action("ISLAFIX", "send_message", {"draft": "Hello"})
        self.assertEqual(self.core.overview("AIBA")["open_tickets"], 0)
        self.assertEqual(self.core.overview("ISLAFIX")["pending_approvals"], 1)
        with self.assertRaises(ValueError):
            self.core.review_action("AIBA", pending, "approved")
        self.core.review_action("ISLAFIX", pending, "approved")
        self.assertEqual(self.core.overview("ISLAFIX")["pending_approvals"], 0)

    def test_balanced_journal_and_duplicates(self):
        n = self.core.post_journal("ISLAFIX", "J001", [
            {"account": "cash", "debit": "100.00"},
            {"account": "revenue", "credit": "100.00"},
        ])
        self.assertEqual(n, 2)
        balances = self.core.overview("ISLAFIX")["ledger_balances_cents"]
        self.assertEqual(balances, {"cash": 10000, "revenue": -10000})
        with self.assertRaises(ValueError):
            self.core.post_journal("ISLAFIX", "J001", [
                {"account": "cash", "debit": "100"},
                {"account": "revenue", "credit": "100"},
            ])
        with self.assertRaises(ValueError):
            self.core.post_journal("ISLAFIX", "J002", [
                {"account": "cash", "debit": "1"},
                {"account": "revenue", "credit": "2"},
            ])
        self.assertEqual(len(self.core.overview("ISLAFIX")["ledger_balances_cents"]), 2)

    def test_draft_only_no_external_actions(self):
        self.core.draft_estimate("AIBA", "Consulting work", "425.90")
        self.assertEqual(self.core.overview("AIBA")["draft_estimates"], 1)
        with self.assertRaises(ValueError):
            self.core.draft_estimate("AIBA", "Invalid", "-1")
        with self.assertRaises(ValueError):
            self.core.draft_estimate("AIBA", "Invalid", "1.005")
        with self.assertRaises(ValueError):
            self.core.propose_action("AIBA", "direct_bank_transfer", {"usd": 100})

    def test_persist_across_processes(self):
        self.core.add_contact("AIBA", "Client A")
        self.core.close()
        self.core = BusinessCore(Path(self.tmp.name) / "business.sqlite3")
        self.assertEqual(self.core.overview("AIBA")["contacts"], 1)

if __name__ == "__main__":
    unittest.main()
