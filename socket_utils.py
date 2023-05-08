import socket
import ssl
import threading
import json
import time
import select
import logging

class StoppableThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            print("Thread running...")
            time.sleep(1)
        print("Thread stopped.")

    def stop(self):
        self._stop_event.set()

class SocketComm:
    """
    Socket communication class
    """

    def __init__(self, type: str = "server", host: str = "localhost", port: int = 8800, use_ssl: bool = False):
        self.acception_thread = None
        self.ssl_sock = None
        self.sock = None
        self._sock = None
        self._ssl_sock = None
        self.type = type
        self.host = host
        self.port = port
        if self.type == "server":
            self.context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        else:
            self.context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        #self.context.set_ciphers('DEFAULT')
        self.use_ssl = use_ssl
        # this doesnt work yet get some weird error from ssl module
        self.connected = False
        self.stop_event = threading.Event()
        self.log = logging.getLogger(f"SocketComm_{self.type}")
        self.log.setLevel(logging.DEBUG)

    def create_socket(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.type == 'client':
            pass
        elif self.type == 'server':
            self._sock.bind((self.host, self.port))
            self._sock.listen()
            if self.use_ssl:
                self._ssl_sock = self.context.wrap_socket(self._sock, server_side=True, do_handshake_on_connect=False)

    def accept_connection(self):
        while not self.stop_event.is_set():
            self.log.debug('waiting for connection...')
            if self.use_ssl:
                ready, _, _ = select.select([self._ssl_sock], [], [], 0.1)
                if ready:
                    self.ssl_sock, self.addr = self._ssl_sock.accept()
                    self.ssl_sock.settimeout(0.1)
                    self.connected = True
                    self.log.info(f"Connected to {self.addr}")
                    break
            else:
                ready, _, _ = select.select([self._sock], [], [], 0.1)
                if ready:
                    self.sock, self.addr = self._sock.accept()
                    self.sock.settimeout(0.1)
                    self.connected = True
                    self.log.info(f"Connected to {self.addr}")
                    break
        else:
            self.log.debug("Stop event set. Stopping thread...")
            return

    def threaded_accept_connection(self):
        """
        Accepts connection in a separate thread, to not block the main thread
        """
        #self.acception_thread = StoppableThread(target=self.accept_connection)
        self.stop_event.clear()
        self.acception_thread = threading.Thread(target=self.accept_connection)
        self.acception_thread.start()

    def stop_waiting_for_connection(self):
        """
        sets the stop event, so the thread will stop waiting for a connection
        """
        self.stop_event.set()

    def connect(self) -> bool:
        """
        Connects to the server
        """
        if self.type == 'client':
            if self.use_ssl:
                self.ssl_sock = self.context.wrap_socket(self._sock, server_hostname=self.host, do_handshake_on_connect=False)
            else:
                self.sock = self._sock
            self._connect(self.host, self.port)
            return True
        else:
            return False
            #raise RuntimeError("Error: Cannot connect on server socket")

    def close_socket(self):
        if self.use_ssl:
            if self.ssl_sock:
                self.ssl_sock.close()
            self._ssl_sock.close()
        if self.sock:
            self.sock.close()
        self._sock.close()
        self.connected = False

    def read_json_message(self) -> dict:
        try:
            message = self._recv_until(b'\n')
            if message is not None:
                message = json.loads(message.decode())
            else:
                return message
        except json.decoder.JSONDecodeError:
            message = None
        return message

    def read_json_message_fast(self) -> dict:
        try:
            message = self._recv(1024)
            if message is not None:
                message = json.loads(message.decode())
            else:
                return message
        except json.decoder.JSONDecodeError:
            message = None
        return message

    def _connect(self, host, port):
        if self.use_ssl:
            self.ssl_sock.connect((host, port))
        else:
            self.sock.connect((host, port))

    def _send(self, data):
        try:
            if self.use_ssl:
                self.ssl_sock.sendall(data)
            else:
                self.sock.sendall(data)
        except ConnectionResetError:
            self.log.error("Connection reset by peer")

    def _recv(self, size) -> bytes:
        try:
            if self.use_ssl:
                return self.ssl_sock.recv(size)
            else:
                return self.sock.recv(size)
        except socket.timeout:
            return None

    def _recv_until(self, delimiter) -> bytes:
        data = b''
        try:
            if self.use_ssl:
                while not data.endswith(delimiter):
                    data += self.ssl_sock.recv(1)
            else:
                while not data.endswith(delimiter):
                    data += self.sock.recv(1)
        except socket.timeout:
            data = None
        return data

    def _recv_all(self):
        data = b''
        if self.use_ssl:
            while True:
                try:
                    data += self.ssl_sock.recv(1024)
                except socket.timeout:
                    break
        else:
            while True:
                try:
                    data += self.sock.recv(1024)
                except socket.timeout:
                    break
        return data


if __name__ == "__main__":
    import time
    import argparse
    import json
    """
    parser = argparse.ArgumentParser(description='Socket communication test')
    parser.add_argument('--type', type=str, default='server', help='Socket type: client or server')
    parser.add_argument('--host', type=str, default='localhost', help='Host IP address')
    parser.add_argument('--port', type=int, default=8800, help='Port number')
    parser.add_argument('--use_ssl', type=bool, default=False, help='Use SSL')
    args = parser.parse_args()

    sock = SocketComm('server')
    sock.create_socket()
    sock.threaded_accept_connection()
    while not sock.connected:
        print('no connection established,waiting...')
        time.sleep(1)
    try:
        data = sock.read_json_message()
        print(data)
    except Exception as e:
        print(e)
        pass
    sock.close_socket()
    """

    import json
    sock = SocketComm('client')
    sock.create_socket()
    sock.connect()
    time.sleep(0.5)
    response = sock.read_json_message_fast()

    print(response)
    message = {'type': 'start_run', 'session_id': 'test', 'setting_file': ''}
    time.sleep(5)
    sock._send(json.dumps(message).encode())
    time.sleep(25)
    message = {'type': 'stop'}
    sock._send(json.dumps(message).encode())
    sock.close_socket()