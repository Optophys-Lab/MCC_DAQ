import time
from socket_utils import SocketComm, SocketMessage

HOST = "127.0.0.1"
PORT = 8800
SESSION_ID = "test_session_001"

daq_sock = SocketComm('client', host=HOST, port=PORT)
daq_sock.create_socket()
daq_sock.connect()
daq_sock.sock.settimeout(2.0)
print("Connected to DAQ")

response = daq_sock.read_json_message()
print("Initial message:", response)

daq_sock.send_json_message({'type': 'status_poll'})
time.sleep(1.0)
response = daq_sock.read_json_message()
print("Status:", response)

# Start DAQ recording
daq_sock.send_json_message({
    'type': 'start_rec',
    'session_id': SESSION_ID,
    'setting_file': '',
    'save_path': ''
})
time.sleep(1.0)
response = daq_sock.read_json_message()
print("Recording response:", response)

input("DAQ recording started... press Enter to stop")

# Stop DAQ recording
daq_sock.send_json_message({'type': 'stop'})
time.sleep(1.0)
response = daq_sock.read_json_message()
print("Stop response:", response)

daq_sock.close_socket()
print("Done")