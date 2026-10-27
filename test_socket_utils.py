import json
import logging
import socket
import threading
import unittest
from types import SimpleNamespace

from socket_utils import SocketComm, SocketMessage


class SocketReadTests(unittest.TestCase):
    def setUp(self):
        self.receiver, self.sender = socket.socketpair()
        self.receiver.settimeout(0.03)
        self.comm = SocketComm()
        self.comm.sock = self.receiver
        self.addCleanup(self.sender.close)
        self.addCleanup(self.receiver.close)

    def test_clean_disconnect_returns_without_freezing_the_gui(self):
        for partial in (b"", b'{"type":'):
            with self.subTest(partial=partial):
                receiver, sender = socket.socketpair()
                receiver.settimeout(0.03)
                comm = SocketComm()
                comm.sock = receiver
                sender.sendall(partial)
                sender.close()
                results = []
                reader = threading.Thread(
                    target=lambda: results.append(comm.read_json_message_fast_linebreak()),
                    daemon=True,
                )
                reader.start()
                try:
                    reader.join(0.5)
                    self.assertFalse(reader.is_alive(), "Socket EOF must not freeze MCC")
                    self.assertEqual(results, [SocketMessage.client_disconnected])
                finally:
                    receiver.close()
                    reader.join(1)

    def test_partial_message_survives_a_poll_timeout(self):
        self.sender.sendall(b'{"type":"status_')
        self.assertIsNone(self.comm.read_json_message_fast_linebreak())
        self.sender.sendall(b'poll"}\n')
        self.assertEqual(
            self.comm.read_json_message_fast_linebreak(), {"type": "status_poll"}
        )

    def test_multiple_messages_are_read_separately(self):
        self.sender.sendall(b'{"type":"status_poll"}\n{"type":"stop"}\n')
        self.assertEqual(
            self.comm.read_json_message_fast_linebreak(), {"type": "status_poll"}
        )
        self.assertEqual(
            self.comm.read_json_message_fast_linebreak(), {"type": "stop"}
        )

    def test_remote_gui_accepts_another_client_after_disconnect(self):
        from GUI_my import MCC_GUI

        self.comm.host = "127.0.0.1"
        self.comm.port = 0
        self.comm.create_socket()
        address = self.comm._sock.getsockname()
        gui = SimpleNamespace(
            socket_comm=self.comm,
            is_remote_ctr=True,
            mcc_board=SimpleNamespace(is_recording=False, is_viewing=False),
            log=logging.getLogger("test"),
        )
        self.sender.close()
        try:
            MCC_GUI.check_and_parse_messages(gui)
            self.assertIsNone(self.comm.sock)
            # Another timer tick while waiting must not start another accept loop.
            MCC_GUI.check_and_parse_messages(gui)
            with socket.create_connection(address, timeout=1) as client:
                self.comm.acception_thread.join(1)
                self.assertFalse(self.comm.acception_thread.is_alive())
                client.sendall(b'{"type":"status_poll"}\n')
                MCC_GUI.check_and_parse_messages(gui)
                with client.makefile("rb") as reader:
                    self.assertEqual(json.loads(reader.readline()), SocketMessage.status_ready)
        finally:
            self.comm.stop_waiting_for_connection()
            if self.comm.acception_thread:
                self.comm.acception_thread.join(1)
            self.comm.close_socket()


if __name__ == "__main__":
    unittest.main()
