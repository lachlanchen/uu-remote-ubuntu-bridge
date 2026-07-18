import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY / "scripts" / "uu_connection_status.py"
SPEC = importlib.util.spec_from_file_location("uu_connection_status", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConnectionStatusTests(unittest.TestCase):
    def test_forced_high_latency_relay_is_reported_without_private_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            log_dir = Path(temporary)
            report = {
                "forced_relay": 1,
                "candidate_type": "relay",
                "average_delay": 346.2,
                "max_delay": 533,
                "streamer_p90_rtt": 402,
                "need_to_p2p_punch": 0,
                "punch_stopped_by_firewall": 0,
                "local_ip": "192.0.2.10",
                "remote_client_id": "private-id",
                "publisher_country": "private-host-region",
                "subscriber_country": "private-controller-region",
            }
            (log_dir / "streamer_log_1.txt").write_text(
                "prefix report json " + json.dumps(report) + "\n"
            )
            (log_dir / "log_1.txt").write_text(
                "insert interrept key: 38 current polinttime is:300 "
                "current client_type is: 1 delay time is:313\n"
            )

            lines, status = MODULE.summarize(log_dir)
            output = "\n".join(lines)

            self.assertEqual(status, 0)
            self.assertIn("relay (forced by controller)", output)
            self.assertIn("average delay: 346 ms", output)
            self.assertIn("threshold 300 ms", output)
            self.assertIn("network-bound input loss is likely", output)
            self.assertIn("relay geography: cross-region", output)
            self.assertIn("check the controlling device's VPN", output)
            self.assertNotIn("192.0.2.10", output)
            self.assertNotIn("private-id", output)
            self.assertNotIn("private-host-region", output)
            self.assertNotIn("private-controller-region", output)

    def test_prior_p2p_block_is_preserved_as_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            log_dir = Path(temporary)
            old = {
                "forced_relay": 0,
                "candidate_type": "relay",
                "average_delay": 500,
                "punch_stopped_by_firewall": 1,
            }
            current = {
                "forced_relay": 1,
                "candidate_type": "relay",
                "average_delay": 300,
                "punch_stopped_by_firewall": 0,
            }
            payload = "".join(
                f"report json {json.dumps(item)}\n" for item in (old, current)
            )
            (log_dir / "streamer_log_1.txt").write_text(payload)

            lines, status = MODULE.summarize(log_dir)

            self.assertEqual(status, 0)
            self.assertIn("earlier automatic sessions", "\n".join(lines))

    def test_latest_report_is_selected_by_log_timestamp_and_stale_is_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            log_dir = Path(temporary)
            old_time = datetime.now() - timedelta(hours=1)
            new_time = datetime.now() - timedelta(minutes=10)
            old = {
                "forced_relay": 0,
                "candidate_type": "relay",
                "average_delay": 900,
            }
            new = {
                "forced_relay": 0,
                "candidate_type": "host",
                "average_delay": 20,
            }
            # Lexical file order deliberately disagrees with session time.
            (log_dir / "streamer_log_z.txt").write_text(
                f"[{old_time:%Y-%m-%d %H:%M:%S.%f}] report json "
                + json.dumps(old)
                + "\n"
            )
            (log_dir / "streamer_log_a.txt").write_text(
                f"[{new_time:%Y-%m-%d %H:%M:%S.%f}] report json "
                + json.dumps(new)
                + "\n"
            )

            lines, status = MODULE.summarize(log_dir)
            output = "\n".join(lines)

            self.assertEqual(status, 0)
            self.assertIn("path: host", output)
            self.assertIn("average delay: 20 ms", output)
            self.assertIn("session is stale", output)


if __name__ == "__main__":
    unittest.main()
