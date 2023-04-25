import copy
from pathlib import Path
import json
import datetime

COLOR_PALETTE = ['#023eff', '#ff7c00', '#1ac938', '#e8000b', '#8b2be2', '#9f4800', '#f14cc1', '#a3a3a3', '#ffc400',
                 '#00d7ff', '#023eff', '#ff7c00', '#1ac938', '#e8000b', '#8b2be2', '#9f4800']
# 'bright' from seaborn
from enum import IntEnum


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
            self.data = np.reshape(data, (self.num_channels, -1))
            self.rec_duration = self.data.shape[1] / self.sampling_rate

class MCC_settings:
    def __init__(self):
        self.num_channels = None
        self.channel_list = []
        self.device = None
        self.voltage_range = None
        self.sampling_rate = 1000
        default_params_file = 'MCC_settings_default.json'
        if Path(default_params_file).exists():
            self.from_file(default_params_file)
        else:
            self.default_setting()

    def to_header(self) -> bytes:
        self.get_active_channels()
        dictionary = copy.deepcopy(vars(self))
        dictionary['datetime'] = datetime.datetime.now().strftime('%Y%m%d_%H%m%S')
        for channel in dictionary['channel_list']:
            channel.pop('color', None)
            channel.pop('win', None)
            channel.pop('active', None)

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


if __name__ == '__main__':
    settings = MCC_settings()
    print(vars(settings))
    settings.to_header()
    print(vars(settings))

    # settings.default_setting()
    #settings.to_file('MCC_settings_default.json')
