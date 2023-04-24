from pathlib import Path
import json

COLOR_PALETTE = ['#023eff', '#ff7c00', '#1ac938', '#e8000b', '#8b2be2', '#9f4800', '#f14cc1', '#a3a3a3', '#ffc400',
                 '#00d7ff', '#023eff', '#ff7c00', '#1ac938', '#e8000b', '#8b2be2', '#9f4800']


# 'bright' from seaborn

class MCC_settings:
    def __init__(self):
        self.channel_list = []
        self.device = None
        self.voltage_range = None
        default_params_file = 'MCC_settings_default.json'
        if Path(default_params_file).exists():
            self.from_file(default_params_file)
        else:
            self.default_setting()

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

    def to_header(self) -> str:
        pass


if __name__ == '__main__':
    settings = MCC_settings()
    #settings.default_setting()
    settings.to_file('MCC_settings_default.json')
