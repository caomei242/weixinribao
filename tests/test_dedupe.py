import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.collector import collect_fixture_messages
from wechat_feedback_app.config import load_config
from wechat_feedback_app.db import connect, init_db


class DedupeTest(unittest.TestCase):
    def test_repeated_fixture_collection_dedupes_raw_messages_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_config(Path("config/app.example.yaml"), root=root)
            config.database.path = str(root / "data" / "test.sqlite3")
            config.wx_cli.fixture_dir = str(Path.cwd() / "fixtures")
            config.export.directory = str(root / "exports")

            conn = connect(config.database.path)
            init_db(conn)

            first = collect_fixture_messages(config, conn)
            second = collect_fixture_messages(config, conn)

            self.assertEqual(first.raw_messages_inserted, 6)
            self.assertEqual(first.raw_messages_duplicated, 1)
            self.assertGreaterEqual(first.candidate_items_created, 5)
            self.assertEqual(second.raw_messages_inserted, 0)
            self.assertEqual(second.raw_messages_duplicated, 7)
            self.assertEqual(second.candidate_items_created, 0)

            raw_count = conn.execute("select count(*) from raw_messages").fetchone()[0]
            item_count = conn.execute("select count(*) from candidate_items").fetchone()[0]
            outside_count = conn.execute(
                "select count(*) from raw_messages where content_text like '%白名单外%'"
            ).fetchone()[0]

            self.assertEqual(raw_count, 6)
            self.assertGreaterEqual(item_count, 5)
            self.assertEqual(outside_count, 0)


if __name__ == "__main__":
    unittest.main()
