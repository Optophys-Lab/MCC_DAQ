import logging
from uldaq import (get_daq_device_inventory, DaqDevice, AInScanFlag,
                   AiInputMode, AiQueueElement, create_float_buffer,
                   ScanOption, ScanStatus, InterfaceType, Range)

class MCCBoard:
    '''Class for acquiring data from a MCC board on a host computer.
    This class may be reused in different gui applications, thus should be a self_sufficent container
    '''
    def __init__(self, file_type='csv'):
        self.log = logging.getLogger('DAQ-Board')
        self.devices = None

    def scan_devices(self) -> list:
        self.devices = get_daq_device_inventory(InterfaceType.USB)
        number_of_devices = len(self.devices)
        if number_of_devices == 0:
            self.log.error('No DAQ devices found')
            raise RuntimeError('Error: No DAQ devices found')

        self.log.debug('Found', number_of_devices, 'DAQ device(s)')

        return [f"{self.devices[i].product_name}_{self.devices[i].unique_id}" for i in range(number_of_devices)]

    def connect_to_device(self, idx):
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
        self.number_of_channels = ai_info.get_num_chans_by_mode(self.input_mode)
        #if high_channel >= number_of_channels:
        #    high_channel = number_of_channels - 1
        #channel_count = high_channel - low_channel + 1

        # Get a list of supported ranges and validate the range index.
        ranges = ai_info.get_ranges(self.input_mode)


        # Allocate a buffer to receive the data.
        #data = create_float_buffer(channel_count, samples_per_channel)