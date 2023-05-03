import copy
from pathlib import Path
import json
import datetime
from PyQt6 import QtWidgets, QtCore, QtGui



COLOR_PALETTE = ['#023eff', '#ff7c00', '#1ac938', '#e8000b', '#8b2be2', '#9f4800', '#f14cc1', '#a3a3a3', '#ffc400',
                 '#00d7ff', '#023eff', '#ff7c00', '#1ac938', '#e8000b', '#8b2be2', '#9f4800']
# 'bright' from seaborn
from enum import IntEnum, Enum, unique

MAX_GRAPHS = 4


@unique
class TimeBases(Enum):
    def __new__(cls, string):
        value = len(cls.__members__)
        obj = object.__new__(cls)
        obj.context = value
        obj._value_ = string
        obj.duration = int(string.split(" ")[0])
        return obj
    s20 = '20 s'
    s10 = '10 s'
    s5 = '5 s'
    s2 = '2 s'
    s1 = '1 s'

@unique
class YRanges(Enum):
    def __new__(cls, string):
        value = len(cls.__members__)
        obj = object.__new__(cls)
        obj.context = value
        obj._value_ = string
        return obj
    birange_10 = '+-10 V'
    birange_5 = '+-5 V'
    birange_3 = '+-3.3 V'
    range_10 = '0-10 V'
    range_5 = '0-5 V'
    range_3 = '0-3.3 V'


class PlotWindowEnum(IntEnum):
    NotVisible = -1
    A = 0
    B = 1
    C = 2
    D = 3
    E = 4
    F = 5
    G = 6
    H = 7
    J = 8
    I = 9
    K = 10
    L = 11

class GraphSettings(QtWidgets.QWidget):
    def __init__(self, nr_of_graphs = 4,idx =0, parent=None):
        super().__init__(parent)
        self._nr_of_graphs = nr_of_graphs
        self.idx = idx  # indicating which viewer this belongs to
        self.layout = QtWidgets.QVBoxLayout(self)
        self.created_elements = []
        self.create_settings_widget()
    @property
    def nr_of_graphs(self):
        return self._nr_of_graphs
    @nr_of_graphs.setter
    def nr_of_graphs(self, value):
        if 0 <= value <= 4:
            self._nr_of_graphs = value
            self.adjust_current_widget()

    def get_current_settings(self) -> dict:
        settings = {}
        for idx in range(self._nr_of_graphs):
            settings[self.graph_name_list[idx].text()] = {}
            settings[self.graph_name_list[idx].text()]["Yrange"] = self.yrange_combo_list[idx].currentText()
            settings[self.graph_name_list[idx].text()]["time_base"] = self.timebase_combo_list[idx].currentText()
        return settings

    def set_current_settings(self, settings):
        for graph in settings.graphsettings.keys():
            for idx in range(4):
                if graph == self.graph_name_list[idx].text():
                    self.yrange_combo_list[idx].setCurrentText(settings.graphsettings[graph]["Yrange"])
                    self.timebase_combo_list[idx].setCurrentText(settings.graphsettings[graph]["time_base"])

    def adjust_current_widget(self):
        for idx in range(4):
            if idx+1 > self._nr_of_graphs:
                self.timebase_combo_list[idx].setEnabled(False)
                self.yrange_combo_list[idx].setEnabled(False)
                self.graph_name_list[idx].setEnabled(False)
                self.tb_list[idx].setEnabled(False)
                self.yr_list[idx].setEnabled(False)
            else:
                self.timebase_combo_list[idx].setEnabled(True)
                self.yrange_combo_list[idx].setEnabled(True)
                self.graph_name_list[idx].setEnabled(True)
                self.tb_list[idx].setEnabled(True)
                self.yr_list[idx].setEnabled(True)
            self.graph_name_list[idx].setText(PlotWindowEnum(MAX_GRAPHS * self.idx + idx).name)
    def create_settings_widget(self):
        #for _ in range(len(self.created_elements)):
        #    el = self.created_elements.pop()
        #    self.layout.removeWidget(el)
        #    #del el

        #print(f'was called with {self._nr_of_graphs}')
        self.timebase_combo_list = []
        self.yrange_combo_list = []
        self.graph_name_list = []
        self.tb_list = []
        self.yr_list = []
        font = QtGui.QFont()
        font.setPointSize(9)
        distance_between_elements = 80
        for idx in range(4):
            graph_name = PlotWindowEnum(MAX_GRAPHS * self.idx + idx).name
            TimeBaseCombo = QtWidgets.QComboBox(parent=self)
            TimeBaseCombo.setGeometry(QtCore.QRect(100, 20+distance_between_elements*idx, 86, 25))
            TimeBaseCombo.setFont(font)
            TimeBaseCombo.setObjectName(f"TimeBaseCombo_{idx}")
            TimeBaseCombo.addItems([e.value for e in TimeBases])
            self.timebase_combo_list.append(TimeBaseCombo)

            YrangeCombo = QtWidgets.QComboBox(parent=self)
            YrangeCombo.setGeometry(QtCore.QRect(100, 50+distance_between_elements*idx, 86, 25))
            YrangeCombo.setFont(font)
            YrangeCombo.setObjectName(f"YrangeCombo_{idx}")
            YrangeCombo.addItems([e.value for e in YRanges])
            self.yrange_combo_list.append(YrangeCombo)

            GName = QtWidgets.QLabel(parent=self)
            GName.setGeometry(QtCore.QRect(0, 0+distance_between_elements*idx, 91, 17))
            GName.setObjectName(f"GName_{idx}")
            GName.setText(graph_name)
            self.graph_name_list.append(GName)

            label_tb = QtWidgets.QLabel(parent=self)
            label_tb.setGeometry(QtCore.QRect(10, 30+distance_between_elements*idx, 91, 17))
            label_tb.setFont(font)
            label_tb.setObjectName(f"label_tb_{idx}")
            label_tb.setText("time base")
            self.tb_list.append(label_tb)
            #self.created_elements.append(label_tb)
            #self.layout.addWidget(label_tb)

            label_yr = QtWidgets.QLabel(parent=self)
            label_yr.setGeometry(QtCore.QRect(10, 50+distance_between_elements*idx, 91, 17))
            label_yr.setFont(font)
            label_yr.setObjectName(f"label_yr_{idx}")
            label_yr.setText("Y Range")
            self.yr_list.append(label_yr)
            #self.layout.addWidget(label_yr)
            #self.created_elements.append(label_yr)


class MyBinaryFile_Reader:
    def __init__(self, file_name):
        self.rec_duration = None
        self.file_name = file_name

        self.sampling_rate = None
        self.device = None
        self.voltage_range = None
        self.channel_names = None
        self.num_channels = None
        self.data = None
        self.header = None
        self.read_file()

    def process_header(self):
        self.num_channels = self.header['num_channels']
        self.channel_names = [channel['name'] for channel in self.header['channel_list']]
        self.voltage_range = self.header['voltage_range']
        self.device = self.header['device']
        self.sampling_rate = self.header['sampling_rate']

    def read_file(self):
        import numpy as np
        with open(self.file_name, 'rb') as fi:
            header_length = int.from_bytes(fi.read(16), 'little')
            self.header = json.loads(fi.read(header_length).decode('utf-8'))
            # print(struct.unpack('f',fi.read(4)))
            self.process_header()
            data = np.fromfile(fi, float)
            len_remainder = len(data) % self.num_channels
            if len_remainder != 0:
                print('Data length is not multiple of channel count !! Cropping..')
                data = data[:-len_remainder]
            self.data = np.reshape(data, (-1, self.num_channels))
            self.rec_duration = self.data.shape[0] / self.sampling_rate

class MCC_settings:
    def __init__(self):
        self.num_channels = None
        self.channel_list = []
        self.device = None
        self.voltage_range = None
        self.sampling_rate = 1000
        self.graphsettings = {}
        default_params_file = 'MCC_settings_default.json'
        if Path(default_params_file).exists():
            self.from_file(default_params_file)
        else:
            self.default_setting()

    def to_header(self) -> bytes:
        self.get_active_channels()
        dictionary = copy.deepcopy(vars(self))
        dictionary['datetime'] = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        ids_topop = []
        for c_id, channel in enumerate(dictionary['channel_list']):
            channel.pop('color', None)
            channel.pop('win', None)
            if not channel["active"]:
                ids_topop.append(c_id)
        dictionary.pop("graphsettings")
        #TODO think if its actually better to keep all names in case more channels are recorded thn indicated !
        for c_id in sorted(ids_topop, reverse=True):
            dictionary['channel_list'].pop(c_id)
        return json.dumps(dictionary).encode()

    def get_active_channels(self):
        active_channels = [ch_id for ch_id, channel in enumerate(self.channel_list) if channel['active']]
        low_channel = min(active_channels)
        high_channel = max(active_channels)
        self.num_channels = high_channel - low_channel + 1
        return low_channel, high_channel

    def default_setting(self, num_channels=16):
        if num_channels == 16:
            self.device = "USB-1608G"
            self.voltage_range = 'BIP5VOLTS'
        elif num_channels == 8:
            self.voltage_range = 'BIP10VOLTS'
            raise NotImplementedError
        else:
            raise NotImplementedError

        for ch_id in range(num_channels):
            channel_dict = {}
            channel_dict['id'] = ch_id
            channel_dict['name'] = f"Channel_{ch_id}"
            channel_dict['active'] = True
            channel_dict['win'] = -1
            channel_dict['color'] = COLOR_PALETTE[ch_id]
            self.channel_list.append(channel_dict)

    def from_file(self, path2file: (str, Path)):
        with open(path2file, 'r') as fi:
            loaded_dict = json.load(fi)
        for key in loaded_dict.keys():
            if key in self.__dict__.keys():
                self.__dict__[key] = loaded_dict[key]

    def to_file(self, path2file: (str, Path)):
        dict_to_save = vars(self)
        with open(path2file, 'w') as fi:
            json.dump(dict_to_save, fi, indent=4)

    def add_graphsettings(self, graphsetting :dict):
        self.graphsettings.update({**graphsetting})

if __name__ == '__main__':
    settings = MCC_settings()
    print(vars(settings))
    settings.to_header()
    print(vars(settings))

    # settings.default_setting()
    #settings.to_file('MCC_settings_default.json')
