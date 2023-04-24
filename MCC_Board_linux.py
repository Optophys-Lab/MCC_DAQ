import logging
import platform

OS_TYPE = platform.system()
if OS_TYPE == 'Linux':
    from uldaq import (get_daq_device_inventory, DaqDevice, AInScanFlag,
                       AiInputMode, AiQueueElement, create_float_buffer,
                       ScanOption, ScanStatus, InterfaceType, Range)
elif OS_TYPE == 'Windows':
    """
    potentially need to add     dll_absolute_path = "C:\\Program Files(x86)\\Measurement Computing\\DAQ\\cbw64.dll"
    to ul.py i
    """
    from mcculw import ul
    from mcculw.ul import get_daq_device_inventory, a_input_mode, create_daq_device
    from mcculw.device_info import DaqDeviceInfo as DaqDevice
    from mcculw.enums import InterfaceType, ErrorCode, ScanOptions, ULRange
    from mcculw.enums import AnalogInputMode as AiInputMode
    from mcculw.ul import ULError

# AnalogInputMode ==  AiInputMode
# DaqDeviceInfo ==  DaqDevice
# ScanOption == ScanOptions
# ULRange == Range

class MCCBoard:
    '''Class for acquiring data from a MCC board on a host computer.
    This class may be reused in different gui applications, thus should be a self_sufficent container
    '''
    def __init__(self, file_type='csv'):
        self.ai_ranges = None
        self.num_channels = None
        self.is_connected = False
        self.log = logging.getLogger('DAQ-Board')
        self.devices = None
        self.daq_device = None
        self.board_num = 0
        self.memhandle = None

    def scan_devices(self) -> list:
        self.devices = get_daq_device_inventory(InterfaceType.USB)
        number_of_devices = len(self.devices)
        if number_of_devices == 0:
            self.log.error('No DAQ devices found')
            raise RuntimeError('Error: No DAQ devices found')

        self.log.debug('Found', number_of_devices, 'DAQ device(s)')

        return [f"{self.devices[i].product_name}_{self.devices[i].unique_id}" for i in range(number_of_devices)]

    def connect_to_device(self, idx):
        if OS_TYPE == 'Linux':
            self.connect_to_device_linux(idx)
        elif OS_TYPE == 'Windows':
            self.connect_to_device_windows(idx)
        else:
            raise NotImplementedError

    def connect_to_device_windows(self, idx):
        ul.create_daq_device(self.board_num, self.devices[idx])

        self.daq_device = DaqDevice(self.board_num)
        if not self.daq_device.supports_analog_input:
            raise Exception('Error: The DAQ device does not support '
                            'analog input')
        else:
            self.ai_info = self.daq_device.get_ai_info()

        print('\nActive DAQ device: ',  self.daq_device.product_name, ' (',
              self.daq_device.unique_id, ')\n', sep='')
        #self.daq_board_name = self.daq_device.product_name
        self.input_mode = AiInputMode.SINGLE_ENDED
        # set to differential mode
        a_input_mode(self.board_num, self.input_mode)
        #todo make an option for oter boards ?

        self.num_channels = self.ai_info.num_chans
        self.ai_ranges = [airange.name for airange in self.ai_info.supported_ranges]

        scan_options = self.ai_info.supported_scan_options
        resolution = self.ai_info.resolution
        self.is_connected = True

    def connect_to_device_linux(self, idx):
        self.daq_device = DaqDevice(self.devices[idx])
        # Get the AiDevice object and verify that it is valid.
        ai_device = self.daq_device.get_ai_device()
        if ai_device is None:
            self.log.error('Error: The DAQ device does not support analog '
                               'input')
            raise RuntimeError('Error: The DAQ device does not support analog '
                               'input')
        # Verify the specified device supports hardware pacing for analog input.
        ai_info = ai_device.get_info()
        if not ai_info.has_pacer():
            raise RuntimeError('\nError: The specified DAQ device does not '
                               'support hardware paced analog input')

        # Establish a connection to the DAQ device.
        descriptor = self.daq_device.get_descriptor()
        self.log.debug('\nConnecting to', descriptor.dev_string, '- please wait...')
        # For Ethernet devices using a connection_code other than the default
        # value of zero, change the line below to enter the desired code.
        self.daq_device.connect(connection_code=0)

        # The default input mode is SINGLE_ENDED.
        self.input_mode = AiInputMode.SINGLE_ENDED
        # If SINGLE_ENDED input mode is not supported, set to DIFFERENTIAL.
        if ai_info.get_num_chans_by_mode(AiInputMode.SINGLE_ENDED) <= 0:
            self.input_mode = AiInputMode.DIFFERENTIAL

        # Get the number of channels and validate the high channel number.
        self.num_channels = ai_info.get_num_chans_by_mode(self.input_mode)


        # Get a list of supported ranges and validate the range index.
        ranges = ai_info.get_ranges(self.input_mode)
        self.ai_ranges = [airange.name for airange in ranges]

        self.is_connected = True
        # Allocate a buffer to receive the data.
        #data = create_float_buffer(channel_count, samples_per_channel)

    def release_device(self):
        if OS_TYPE == 'Linux':
            if self.daq_device:
                self.daq_device.disconnect()
                self.daq_device.release()
        else:
            if self.memhandle:
                # Free the buffer in a finally block to prevent a memory leak.
                ul.win_buf_free(self.memhandle)
            ul.release_daq_device(self.board_num)

