import json
import logging
import queue
import sys
import numpy as np
from queue import Queue, Empty

from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog
from PyQt6.QtCore import Qt, QTimer
from PyQt6 import uic, QtGui
import pyqtgraph as pg

from pathlib import Path
from datetime import datetime

from MCC_Board_linux import MCCBoard
from GUI_utils import MCC_settings, PlotWindowEnum, COLOR_PALETTE

log = logging.getLogger('main')
log.setLevel(logging.DEBUG)

#logging.basicConfig(filename='GUI.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')

VERSION = "0.2.0"


class MCC_GUI(QMainWindow):
    def __init__(self):
        super(MCC_GUI, self).__init__()
        self.rec_timer = None
        self.plot_timer = None
        self.path2file = Path(__file__)
        uic.loadUi(self.path2file.parent / 'GUI' / 'GUI.ui', self)
        self.setWindowTitle('MCCRecorder v.%s' % VERSION)
        self.log = logging.getLogger('GUI')
        self.log.setLevel(logging.DEBUG)
        self.daq_device = None
        self.mcc_board = MCCBoard()
        self.ConnectSignals()
        self.ConnectButton.setIcon(QtGui.QIcon("GUI/icons/connect.svg"))
        self.RUNButton.setIcon(QtGui.QIcon("GUI/icons/play.svg"))
        self.RECButton.setIcon(QtGui.QIcon("GUI/icons/record.svg"))
        self.STOPButton.setIcon(QtGui.QIcon("GUI/icons/stop.svg"))
        self.settings = MCC_settings()
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

        for ele in self.channel_win:
            ele.clear()
            ele.addItems([a.name for a in PlotWindowEnum])
            ele.setCurrentIndex(0)
        # self.tabWidget.setTabVisible(1, False)
        # TODO uncomment to hide viewer?

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

    def connect_to_device(self):
        """
        calls the MCCBoard class to connect to chosen device
        """
        idx = self.Device_dropdown.currentIndex()
        self.mcc_board.connect_to_device(idx)
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

            self.set_settings()

    def run_daq(self):
        """
        calls the MCCBoard class to start acquiring data, visualize the data
        """
        self.STOPButton.setEnabled(True)
        self.tabWidget.setCurrentIndex(1)
        self.log.warning('Not Implemented !')

    def record_daq(self):
        """
        calls the MCCBoard class to start recording the choosen data
        """
        self.STOPButton.setEnabled(True)
        self.tabWidget.setCurrentIndex(1)
        self.get_settings()
        self.mcc_board.start_recording(self.settings, True)

        #self.timer = pg.QtCore.QTimer()
        self.reset_plots()
        self.recording_Info.setText('ON')
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        self.plot_timer.start(100)

        self.s_since_start = 0
        self.rec_timer = QTimer()
        self.rec_timer.timeout.connect(self.increase_time)
        self.rec_timer.start(1000)

    def stop_daq(self):
        """
        calls the MCCBoard class to stop recording and acquisition of data
        """
        if self.plot_timer:
            self.plot_timer.stop()

        if self.rec_timer:
            self.rec_timer.stop()

        self.recording_Info.setText('OFF')
        self.mcc_board.stop_recording()

        self.STOPButton.setEnabled(False)
        self.RUNButton.setEnabled(True)
        self.RECButton.setEnabled(True)

        self.plot_timer = None
        self.rec_timer = None

    #### PLOTTING ######
    def reset_plots(self):
        self.plotting_widgets= [self.Channel_viewWidget_1, self.Channel_viewWidget_2, self.Channel_viewWidget_3,
                                self.Channel_viewWidget_4,  self.Channel_viewWidget_5, self.Channel_viewWidget_6,
                                self.Channel_viewWidget_7, self.Channel_viewWidget_8]
        self.plotting_indexing_vec = list()
        for win_id in range(8):
            self.plotting_widgets[win_id].reset(self.settings, win_id=win_id)
            index_vec = []
            for ch_id, channel in enumerate(self.settings.channel_list):
                if channel['win'] == win_id and channel['active']:
                    index_vec.append(ch_id)
            self.plotting_indexing_vec.append(index_vec)

    def update_plots(self):
        # analyze the perfect size for this update ? changing from 100 to 500 seemed to improve a lot.
        # todo maybe add a visualizer of the queu size ?
        value_array = np.zeros((self.settings.num_channels, 500))
        array_step = 0
        for array_step in range(500):
            try:
                for q_id, queue in enumerate(self.mcc_board.data_queues):
                    value_array[q_id, array_step] = queue.get(False)
            except Empty:
                break
        if array_step == 500:
            print('queue is not being emptied fast enough !')
        value_array = value_array[:, :array_step]

        if value_array.shape[1] == 0:  # no new data was acquired between calls
            return


        for plot_widget, index_vec in zip(self.plotting_widgets, self.plotting_indexing_vec):
            if index_vec:
                plot_widget.update_new([value_array[index, :] for index in index_vec])
        # TODO second plot per window doesn not Work !!!!
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
            self.settings.from_file(Path(settings_file[0]))
            self.set_settings()

    def get_settings(self):
        self.settings.channel_list = list()
        for ch_id, (ch_name, ch_rec, ch_win) in enumerate(zip(self.channel_names, self.channel_rec, self.channel_win)):
            if not ch_name.isEnabled():  # skip inactvated channels
                continue
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

    def set_settings(self):
        voltage_set = [idx for idx, r in enumerate(self.mcc_board.ai_ranges) if r == self.settings.voltage_range]
        if not voltage_set:
            voltage_set = 0
            self.log.info('Voltage Range from settings is not supported by this board\nSetting default one')
        else:
            voltage_set = voltage_set[0]

        self.Range_combo.setCurrentIndex(voltage_set)
        self.SamplingRateSpin.setValue(self.settings.sampling_rate)
        for c_id, channel in enumerate(self.settings.channel_list):
            self.channel_labels[c_id].setStyleSheet(f"color: {channel['color']};")
            self.channel_names[c_id].setText(channel['name'])
            self.channel_rec[c_id].setChecked(channel['active'])
            self.channel_win[c_id].setCurrentText(PlotWindowEnum(channel["win"]).name)

    #### APP MAINTANCE #######
    def ConnectSignals(self):
        self.ScanDevButton.clicked.connect(self.scan_devices)
        self.ConnectButton.clicked.connect(self.connect_to_device)
        self.RUNButton.clicked.connect(self.run_daq)
        self.RECButton.clicked.connect(self.record_daq)
        self.STOPButton.clicked.connect(self.stop_daq)

        self.SettingsSaveButton.clicked.connect(self.save_settings)
        self.SettingsLoadButton.clicked.connect(self.load_settings)

    def app_is_exiting(self):
        if self.mcc_board.is_recording:
            self.mcc_board.stop_recording()
        if self.mcc_board.daq_device:
            self.mcc_board.release_device()

    def closeEvent(self, event):
        self.log.info("Received window close event.")
        # todo add a check if recording is running ? prevent from closing ? or open dialog
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
