import json
import logging
import queue
import sys

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import Qt, QTimer
from PyQt6 import uic

from pathlib import Path
from datetime import datetime


log = logging.getLogger('main')
log.setLevel(logging.DEBUG)

logging.basicConfig(filename='GUI_full.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')

VERSION = "0.0.0"


from uldaq import (get_daq_device_inventory, DaqDevice, AInScanFlag,
                   AiInputMode, AiQueueElement, create_float_buffer,
                   ScanOption, ScanStatus, InterfaceType, Range)

class MCC_GUI(QMainWindow):
    def __init__(self):
        super(MCC_GUI, self).__init__()
        self.path2file = Path(__file__)
        uic.loadUi(self.path2file.parent / 'GUI' / 'GUI.ui', self)
        self.setWindowTitle('MCCRecorder v.%s' % VERSION)
        self.log = logging.getLogger('GUI')

        self.daq_device = None

        self.ConnectSignals()
    def scan_devices(self):
        self.Device_dropdown.clear()
        self.Device_dropdown.addItems(self.daq_device.scan_devices())

    def connect_to_device(self):
        ## TODO Move this to oits own class !!!!
        idx = self.Device_dropdown.currentIndex()
        self.daq_device.connect(idx)



    #### APP MAINTANCE #######
    def ConnectSignals(self):
        self.ScanDevButton.clicked.connect(self.scan_devices)
        self.ConnectButton.clicked.connect(self.connect_to_device)
    def app_is_exiting(self):
        if self.daq_device:
            if self.daq_device.is_connected():
                self.daq_device.disconnect()
            self.daq_device.release()

    def closeEvent(self, event):
        self.log.info("Received window close event.")
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

