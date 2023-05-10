"""
Tool to record using MCC DAQ Devices.

Author: Artur
Contact: artur.schneider@biologie.uni-freiburg.de

Features:
- recording selected channels in binary file
- pulsation functionality
- visualization of selected channels in configurable graphs
- settings can be set/loaded from file
- can be controlled remotely via socket connection
- only 16 channel model 1608 was tested

maybe:
- implement trigger mode ? wait for digital signal to start recording ?
"""

import json
import logging
import queue
import sys
import numpy as np
from queue import Queue, Empty

from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6 import uic, QtGui
import pyqtgraph as pg

from pathlib import Path
from datetime import datetime

from MCC_Board_linux import MCCBoard
from GUI_utils import MCC_settings, PlotWindowEnum, COLOR_PALETTE, MAX_GRAPHS, RemoteConnDialog
from socket_utils import SocketComm

log = logging.getLogger('main')
log.setLevel(logging.DEBUG)

# logging.basicConfig(filename='GUI.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')

VERSION = "0.4.1"
UPDATE_GRAPHS_TIME = 100  # ms
COUNTER_UPDATE_TIME = 1000  # ms
HOST = "localhost" # if connecting to remote, use the IP of the current machine
PORT = 8800


class MCC_GUI(QMainWindow):
    def __init__(self):
        super(MCC_GUI, self).__init__()
        self.is_remote_ctr = False
        self.counter_timer = None
        self.rec_timer = None
        self.plot_timer = None
        self.path2file = Path(__file__)
        uic.loadUi(self.path2file.parent / 'GUI' / 'GUI.ui', self)
        self.setWindowTitle('MCCRecorder v.%s' % VERSION)

        self.log = logging.getLogger('GUI')
        self.log.setLevel(logging.DEBUG)
        self.daq_device = None
        self.mcc_board = MCCBoard()
        self.ConnectButton.setIcon(QtGui.QIcon("GUI/icons/connect.svg"))
        self.RUNButton.setIcon(QtGui.QIcon("GUI/icons/play.svg"))
        self.RECButton.setIcon(QtGui.QIcon("GUI/icons/record.svg"))
        self.STOPButton.setIcon(QtGui.QIcon("GUI/icons/stop.svg"))
        self.RemoteModeButton.setIcon(QtGui.QIcon("GUI/icons/Signal.svg"))
        self.tabWidget.setTabIcon(1, QtGui.QIcon("GUI/icons/WrenchScrewdriver.svg"))
        self.tabWidget.setTabIcon(2, QtGui.QIcon("GUI/icons/Window.svg"))
        self.tabWidget.setTabIcon(3, QtGui.QIcon("GUI/icons/Window.svg"))
        self.tabWidget.setTabIcon(4, QtGui.QIcon("GUI/icons/Window.svg"))
        self.settings = MCC_settings()
        self.socket_comm = SocketComm(type='server', host=HOST, port=PORT)
        self.socket_comm.create_socket()

        # Dynamically Create ?
        self.channel_labels = [self.CH_0, self.CH_1, self.CH_2, self.CH_3, self.CH_4, self.CH_5, self.CH_6, self.CH_7,
                               self.CH_8, self.CH_9, self.CH_10, self.CH_11, self.CH_12, self.CH_13, self.CH_14,
                               self.CH_15]
        self.channel_names = [self.CH_name_0, self.CH_name_1, self.CH_name_2, self.CH_name_3, self.CH_name_4,
                              self.CH_name_5, self.CH_name_6, self.CH_name_7, self.CH_name_8, self.CH_name_9,
                              self.CH_name_10, self.CH_name_11, self.CH_name_12, self.CH_name_13, self.CH_name_14,
                              self.CH_name_15]
        self.channel_rec = [self.CH_REC_0, self.CH_REC_1, self.CH_REC_2, self.CH_REC_3, self.CH_REC_4,
                            self.CH_REC_5, self.CH_REC_6, self.CH_REC_7, self.CH_REC_8, self.CH_REC_9,
                            self.CH_REC_10, self.CH_REC_11, self.CH_REC_12, self.CH_REC_13, self.CH_REC_14,
                            self.CH_REC_15]
        self.channel_win = [self.CH_Win_0, self.CH_Win_1, self.CH_Win_2, self.CH_Win_3, self.CH_Win_4,
                            self.CH_Win_5, self.CH_Win_6, self.CH_Win_7, self.CH_Win_8, self.CH_Win_9,
                            self.CH_Win_10, self.CH_Win_11, self.CH_Win_12, self.CH_Win_13, self.CH_Win_14,
                            self.CH_Win_15]

        self.Viewer1_Combo.addItems(map(str, range(5)))
        self.Viewer2_Combo.addItems(map(str, range(5)))
        self.Viewer3_Combo.addItems(map(str, range(5)))
        self.Viewer1_Combo.setCurrentIndex(4)
        self.Viewer2_Combo.setCurrentIndex(4)
        self.Viewer3_Combo.setCurrentIndex(4)

        self.Graph_setting_1.idx = 0
        self.Graph_setting_1.adjust_current_widget()
        self.Graph_setting_2.idx = 1
        self.Graph_setting_2.adjust_current_widget()
        self.Graph_setting_3.idx = 2
        self.Graph_setting_3.adjust_current_widget()

        self.Channel_viewWidget_1.idx = 0
        self.Channel_viewWidget_2.idx = 1
        self.Channel_viewWidget_3.idx = 2

        self.ConnectSignals()
        for ele in self.channel_win:
            ele.clear()
            ele.addItems([a.name for a in PlotWindowEnum])
            ele.setCurrentIndex(0)
        # self.tabWidget.setTabVisible(1, False)

        self.scan_devices()

    ### DAQ Board interaction
    def scan_devices(self):
        """
        calls the MCCBoard class to scan available devices and displays them in dropdown
        """
        self.Device_dropdown.clear()
        devices = self.mcc_board.scan_devices()
        if devices:  # found devices
            self.Device_dropdown.addItems(devices)
            self.ConnectButton.setEnabled(True)
        self.log.debug(f'Scanned for available devices')

        if len(devices) == 1:
            self.connect_to_device()
            self.log.debug(f'Connecting to only device automatically')

    def connect_to_device(self):
        """
        calls the MCCBoard class to connect to chosen device
        """
        idx = self.Device_dropdown.currentIndex()
        self.mcc_board.connect_to_device(idx)
        self.mcc_board.reset_counters()
        self.log.debug(f'Connecting to {idx} device')
        if self.mcc_board.ai_ranges:
            self.Range_combo.clear()
            self.Range_combo.addItems(self.mcc_board.ai_ranges)
        if self.mcc_board.is_connected:
            self.ConnectButton.setEnabled(False)
            self.RUNButton.setEnabled(True)
            self.RECButton.setEnabled(True)
            # self.tabWidget.setTabVisible(1, True)
            for c_id in range(self.mcc_board.num_channels):
                self.channel_labels[c_id].setEnabled(True)
                self.channel_names[c_id].setEnabled(True)
                self.channel_rec[c_id].setEnabled(True)
                self.channel_win[c_id].setEnabled(True)
            # pop channels not available ?

            self.set_settings()
        self.ScanDevButton.setEnabled(False)

    def run_daq(self):
        """
        calls the MCCBoard class to start acquiring data, visualize the data
        """
        self.get_settings()
        self.mcc_board.reset_counters()
        self.mcc_board.start_viewing(self.settings)

        self.reset_plots()
        self.recording_Info.setText('Viewing')
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        self.plot_timer.start(UPDATE_GRAPHS_TIME)
        self.s_since_start = 0
        self.rec_timer = QTimer()
        self.rec_timer.timeout.connect(self.increase_time)
        self.rec_timer.start(1000)

        if self.settings.scan_counters:
            self.counter_timer = QTimer()
            self.counter_timer.timeout.connect(self.get_counter_vals)
            self.counter_timer.start(COUNTER_UPDATE_TIME)

        self.RUNButton.setEnabled(False)
        self.RECButton.setEnabled(False)

        self.STOPButton.setEnabled(True)
        self.tabWidget.setCurrentIndex(2)
        self.tabWidget.setTabEnabled(1, False)

    def record_daq(self):
        """
        calls the MCCBoard class to start recording the chosen data
        """
        self.get_settings()
        self.mcc_board.reset_counters()
        self.mcc_board.start_recording(self.settings)

        # self.timer = pg.QtCore.QTimer()
        self.reset_plots()
        self.recording_Info.setText('ON')
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        self.plot_timer.start(UPDATE_GRAPHS_TIME)

        self.s_since_start = 0
        self.rec_timer = QTimer()
        self.rec_timer.timeout.connect(self.increase_time)
        self.rec_timer.start(1000)

        if self.settings.scan_counters:
            self.counter_timer = QTimer()
            self.counter_timer.timeout.connect(self.get_counter_vals)
            self.counter_timer.start(COUNTER_UPDATE_TIME)

        self.RUNButton.setEnabled(False)
        self.RECButton.setEnabled(False)
        self.CounterScanButton.setEnabled(False)
        self.STOPButton.setEnabled(True)
        self.tabWidget.setCurrentIndex(2)
        self.tabWidget.setTabEnabled(1, False)

    def stop_daq(self):
        """
        calls the MCCBoard class to stop recording and acquisition of data
        """
        if self.plot_timer:
            self.plot_timer.stop()

        if self.rec_timer:
            self.rec_timer.stop()

        if self.counter_timer:
            self.counter_timer.stop()

        self.recording_Info.setText('OFF')
        self.mcc_board.stop_recording()

        self.STOPButton.setEnabled(False)
        if not self.is_remote_ctr:
            self.RUNButton.setEnabled(True)
            self.RECButton.setEnabled(True)
            self.CounterScanButton.setEnabled(True)
            self.tabWidget.setTabEnabled(1, True)

        self.plot_timer = None
        self.rec_timer = None

    def get_counter_vals(self):
        """
        polls mcc board for the counters status
        display available counter values
        """
        counter_vals = self.mcc_board.get_single_counter()
        for val, display in zip(counter_vals, [self.counterDisplay_1, self.counterDisplay_2]):
            display.display(val)

    def start_stop_pulses(self):
        """
        calls mcc_board to start or stop pulsing with a chosen frequency
        """
        if not self.mcc_board.is_pulsing:
            # start pulsing
            self.mcc_board.start_pulsing(self.PulsesSpin.value())
            self.StartSignalButton.setText('Stop Pulsing')
        else:
            # stop pulsing
            self.StartSignalButton.setText('Start Pulsing')
            self.mcc_board.stop_pulsing()

    #### PLOTTING ######
    def reset_plots(self):
        self.plotting_widgets = []
        plotting_indx = []
        for multi_view_graph in [self.Channel_viewWidget_1, self.Channel_viewWidget_2, self.Channel_viewWidget_3]:
            self.plotting_widgets.extend(multi_view_graph.list_of_plots)
            plotting_indx.extend([val + multi_view_graph.idx * MAX_GRAPHS
                                  for val in range(len(multi_view_graph.list_of_plots))])
        self.plotting_indexing_vec = list()

        for idx, win_id in enumerate(plotting_indx):
            self.plotting_widgets[idx].reset(self.settings, win_id=win_id)
            index_vec = []
            for ch_id, channel in enumerate(self.settings.channel_list):
                if channel['win'] == win_id and channel['active']:
                    index_vec.append(ch_id)
            self.plotting_indexing_vec.append(index_vec)

    def update_plots(self):
        # analyze the perfect size for this update ? changing from 100 to 500 seemed to improve a lot.
        value_array = np.zeros((self.settings.num_channels, 500))
        array_step = 0
        for array_step in range(500):
            try:
                for q_id, queue in enumerate(self.mcc_board.data_queues):
                    value_array[q_id, array_step] = queue.get(False)
            except Empty:
                break
        if array_step == 500:
            self.log.warning('queue is not being emptied fast enough !')
        value_array = value_array[:, :array_step]

        if value_array.shape[1] == 0:  # no new data was acquired between calls
            return

        for plot_widget, index_vec in zip(self.plotting_widgets, self.plotting_indexing_vec):
            if index_vec:
                plot_widget.update_new([value_array[index, :] for index in index_vec])

        self.statusbar.showMessage(f"In Q :{self.mcc_board.data_queues[0].qsize()}")
        # todo indicate the lag ?

    def increase_time(self):
        """
        counts the recording time up each second and displays it
        """
        self.s_since_start = self.s_since_start + 1
        self.timer_info.setText(f'{int(self.s_since_start / 60):02d}:{self.s_since_start % 60:02d}')

    ##### SETTINGS ######
    def save_settings(self):
        settings_file = QFileDialog.getSaveFileName(self, 'Save settings file', "",
                                                    "Settings files (*.json)")
        if settings_file[0]:
            self.get_settings()
            self.settings.to_file(settings_file[0])

    def load_settings(self):
        settings_file = QFileDialog.getOpenFileName(self, 'Open settings file', "",
                                                    "Settings files (*.json)")
        if settings_file[0]:
            self.load_settings_fromfile(settings_file[0])

    def load_settings_fromfile(self, settings_file):
        self.settings.from_file(Path(settings_file))
        self.set_settings()

    def get_settings(self):
        self.settings.channel_list = list()
        for ch_id, (ch_name, ch_rec, ch_win) in enumerate(zip(self.channel_names, self.channel_rec, self.channel_win)):
            #if not ch_name.isEnabled():  # skip inactvated channels
            #    continue
            # this lead to a bug where the channel list was not updated when a channel was disabled because whole tab
            # was disabled
            #TODO find a better way to adjust number of channels!
            channel_dict = {}
            channel_dict['id'] = ch_id
            channel_dict['name'] = ch_name.text()
            channel_dict['active'] = ch_rec.isChecked()
            channel_dict['win'] = PlotWindowEnum[ch_win.currentText()].value
            channel_dict['color'] = COLOR_PALETTE[ch_id]
            self.settings.channel_list.append(channel_dict)

        self.settings.voltage_range = self.Range_combo.currentText()
        try:
            self.settings.device = self.mcc_board.daq_device.product_name
        except AttributeError:
            self.settings.device = self.Device_dropdown.currentText()

        self.settings.sampling_rate = self.SamplingRateSpin.value()
        self.settings.get_active_channels()

        self.settings.graphsettings = {}
        self.settings.add_graphsettings(self.Graph_setting_1.get_current_settings())
        self.settings.add_graphsettings(self.Graph_setting_2.get_current_settings())
        self.settings.add_graphsettings(self.Graph_setting_3.get_current_settings())

        self.settings.scan_counters = self.Counters_checkBox.isChecked()

    def set_settings(self):
        voltage_set = [idx for idx, r in enumerate(self.mcc_board.ai_ranges) if r == self.settings.voltage_range]
        if not voltage_set:
            voltage_set = 0
            self.log.info('Voltage Range from settings is not supported by this board\nSetting default one')
        else:
            voltage_set = voltage_set[0]

        self.Range_combo.setCurrentIndex(voltage_set)
        self.SamplingRateSpin.setValue(self.settings.sampling_rate)
        self.set_graph_options()
        for c_id, channel in enumerate(self.settings.channel_list):
            self.channel_labels[c_id].setStyleSheet(f"color: {channel['color']};")
            self.channel_names[c_id].setText(channel['name'])
            self.channel_rec[c_id].setChecked(channel['active'])
            self.channel_win[c_id].setCurrentText(PlotWindowEnum(channel["win"]).name)

        self.Graph_setting_1.set_current_settings(self.settings)
        self.Graph_setting_2.set_current_settings(self.settings)
        self.Graph_setting_3.set_current_settings(self.settings)
        self.set_nr_graths()

        self.Counters_checkBox.setChecked(self.settings.scan_counters)

    def set_graph_options(self):
        for ele in self.channel_win:
            curr_element = ele.currentText()
            ele.clear()
            elements = [PlotWindowEnum(-1).name]
            elements.extend(list(self.settings.graphsettings.keys()))
            ele.addItems(elements)
            try:
                next_index = [idx for idx, name in enumerate(elements) if name == curr_element][0]
                ele.setCurrentIndex(next_index)
            except IndexError:
                ele.setCurrentIndex(0)

    def set_nr_graths(self):
        for idx in range(3):
            counter = 0
            for active_graphs in self.settings.graphsettings.keys():
                if active_graphs in [el.name for el in list(PlotWindowEnum)[1 + idx * MAX_GRAPHS:5 + idx * MAX_GRAPHS]]:
                    counter += 1
            if idx == 0:
                self.Viewer1_Combo.setCurrentText(str(counter))
            elif idx == 1:
                self.Viewer2_Combo.setCurrentText(str(counter))
            elif idx == 2:
                self.Viewer3_Combo.setCurrentText(str(counter))

    #### APP MAINTANCE #######
    def ConnectSignals(self):
        self.ScanDevButton.clicked.connect(self.scan_devices)
        self.ConnectButton.clicked.connect(self.connect_to_device)
        self.RUNButton.clicked.connect(self.run_daq)
        self.RECButton.clicked.connect(self.record_daq)
        self.STOPButton.clicked.connect(self.stop_daq)

        self.CounterScanButton.clicked.connect(self.get_counter_vals)
        self.StartSignalButton.clicked.connect(self.start_stop_pulses)

        self.SettingsSaveButton.clicked.connect(self.save_settings)
        self.SettingsLoadButton.clicked.connect(self.load_settings)

        self.Viewer1_Combo.currentIndexChanged.connect(self.adjust_viewer1)
        self.Viewer2_Combo.currentIndexChanged.connect(self.adjust_viewer2)
        self.Viewer3_Combo.currentIndexChanged.connect(self.adjust_viewer3)

        self.RemoteModeButton.clicked.connect(self.remote_mode)

    def adjust_viewer1(self):
        self.Graph_setting_1.nr_of_graphs = int(self.Viewer1_Combo.currentText())
        self.Channel_viewWidget_1.nr_plots = int(self.Viewer1_Combo.currentText())
        self.get_settings()
        self.set_graph_options()

    def adjust_viewer2(self):
        self.Graph_setting_2.nr_of_graphs = int(self.Viewer2_Combo.currentText())
        self.Channel_viewWidget_2.nr_plots = int(self.Viewer2_Combo.currentText())
        self.get_settings()
        self.set_graph_options()

    def adjust_viewer3(self):
        self.Graph_setting_3.nr_of_graphs = int(self.Viewer3_Combo.currentText())
        self.Channel_viewWidget_3.nr_plots = int(self.Viewer3_Combo.currentText())
        self.get_settings()
        self.set_graph_options()

    def remote_mode(self):
        if not self.socket_comm.connected:
            self.socket_comm.threaded_accept_connection()
            remote_dialog = RemoteConnDialog(self.socket_comm, self)
            remote_dialog.exec()

            if not self.socket_comm.connected:
                self.log.debug('Aborted remote connection')
            else:
                self.log.debug('Connected')
                self.enter_remote_mode()

        else:
            # self.abort_remoteconnection()
            self.exit_remote_mode()

    def enter_remote_mode(self):
        self.Client_label.setText(f"Connected to Client:\n{self.socket_comm.addr}")
        self.RemoteModeButton.setText("EXIT\nREMOTE-mode")
        self.RemoteModeButton.setIcon(QtGui.QIcon("GUI/icons/SignalSlash.svg"))
        self.RUNButton.setEnabled(False)
        self.RECButton.setEnabled(False)
        self.tabWidget.setTabEnabled(1, False)
        self.tabWidget.setTabEnabled(0, False)
        self.tabWidget.setCurrentIndex(2)
        self.remote_message_timer = QTimer()
        self.remote_message_timer.timeout.connect(self.check_and_parse_messages)
        self.remote_message_timer.start(500)
        self.is_remote_ctr = True
        self.socket_comm._send(json.dumps({"type": "status", "status": "ready"}).encode())

    def exit_remote_mode(self):
        self.socket_comm.close_socket()
        self.Client_label.setText("disconnected")
        self.RemoteModeButton.setText("ENTER\nREMOTE-mode")
        if self.remote_message_timer:
            self.remote_message_timer.stop()
            self.remote_message_timer = None
        self.is_remote_ctr = False
        self.RUNButton.setEnabled(True)
        self.RECButton.setEnabled(True)
        self.tabWidget.setTabEnabled(1, True)
        self.tabWidget.setTabEnabled(0, True)

    def check_and_parse_messages(self):
        message = self.socket_comm.read_json_message_fast()
        if message:
            # parse message
            if message['type'] == 'start_rec':
                self.log.info("got message to start recording")
                try:
                    if message["setting_file"]:
                        self.load_settings_fromfile(message["setting_file"])
                        self.log.debug(f"loaded settings from {message['setting_file']}")
                except (FileNotFoundError, KeyError):
                    self.log.error("passed settings file not found")

                self.settings.session_name = message["session_id"]
                self.session_label.setText(self.settings.session_name)
                self.remote_message_timer.setInterval(10000)  # increase the interval to 10s
                self.record_daq()
                response = {"type": "response", "status": "recording_ok"}
                self.socket_comm._send(json.dumps(response).encode())

            elif message['type'] == 'stop':
                self.log.info("got message to stop")
                self.stop_daq()
                self.remote_message_timer.setInterval(500)
                response = {"type": "response", "status": "stop_ok"}
                self.socket_comm._send(json.dumps(response).encode())

            elif message['type'] == 'status_poll':
                if self.mcc_board.is_recording:
                    response = {"type": "status", "status": "recording"}
                elif self.mcc_board.is_viewing:
                    response = {"type": "status", "status": "viewing"}
                elif self.is_remote_ctr:
                    response = {"type": "status", "status": "ready"}
                else:
                    response = {"type": "status", "status": "error"}
                self.socket_comm._send(json.dumps(response).encode())

            elif message['type'] == 'start_run':
                self.log.info("got message to start viewing")
                try:
                    if message["setting_file"]:
                        self.load_settings_fromfile(message["setting_file"])
                except (FileNotFoundError, KeyError):
                    self.log.error("passed settings file not found")

                self.settings.session_name = message["session_id"]
                self.session_label.setText(self.settings.session_name)
                self.remote_message_timer.setInterval(10000) #increase the interval to 10s
                self.run_daq()
                response = {"type": "response", "status": "run_ok"}
                self.socket_comm._send(json.dumps(response).encode())

    def check_connection(self):
        if self.socket_comm.connected:
            self.remote_dialog.close()

    def abort_remoteconnection(self):
        self.socket_comm.stop_waiting_for_connection()

    def app_is_exiting(self):
        if self.mcc_board.is_recording or self.mcc_board.is_viewing:
            self.mcc_board.stop_recording()
        if self.mcc_board.daq_device:
            self.mcc_board.release_device()

    def closeEvent(self, event):
        self.log.info("Received window close event.")
        if self.mcc_board.is_recording:
            message = QMessageBox.information(self,
                                              "Recording is active",
                                              "Recording still running. Abort ?",
                                              buttons=QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes)
            if message == QMessageBox.StandardButton.No:
                event.ignore()
                return
            elif message == QMessageBox.StandardButton.Abort:
                event.ignore()
                return
            elif message == QMessageBox.StandardButton.Yes:
                self.log.info('not exiting')
        self.app_is_exiting()
        # self.disable_console_logging()
        super(MCC_GUI, self).closeEvent(event)


def start_gui():
    app = QApplication([])
    win = MCC_GUI()
    win.show()
    app.exec()


if __name__ == '__main__':
    logging.info('Starting via __main__')
    sys.exit(start_gui())
