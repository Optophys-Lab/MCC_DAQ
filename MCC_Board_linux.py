import logging
import platform
from pathlib import Path
from ctypes import c_double, cast, POINTER, addressof, sizeof
from threading import Thread, Event
from queue import Queue, Full, Empty
import json
import struct
import time
import datetime

import numpy as np


from GUI_utils import MCC_settings

OS_TYPE = platform.system()
if OS_TYPE == 'Linux':
    from uldaq import (get_daq_device_inventory, DaqDevice, AInScanFlag,
                       AiInputMode, AiQueueElement, create_float_buffer,
                       ScanStatus, InterfaceType, TmrIdleState, PulseOutOption)
    from uldaq import ScanOption as ScanOptions
    from uldaq import Range as ULRange
    from uldaq import ScanStatus as Status
    import uldaq.ul_exception

elif OS_TYPE == 'Windows':
    """
    potentially need to add     dll_absolute_path = "C:\\Program Files(x86)\\Measurement Computing\\DAQ\\cbw64.dll"
    to ul.py i
    """
    from mcculw import ul
    from mcculw.ul import get_daq_device_inventory, a_input_mode, create_daq_device
    from mcculw.device_info import DaqDeviceInfo as DaqDevice
    from mcculw.enums import InterfaceType, ErrorCode, ScanOptions, ULRange, Status, FunctionType, CounterChannelType
    from mcculw.enums import AnalogInputMode as AiInputMode
    from mcculw.ul import ULError


# AnalogInputMode ==  AiInputMode
# DaqDeviceInfo ==  DaqDevice


class MCCBoard:
    '''Class for acquiring data from a MCC board on a host computer.
    This class may be reused in different gui applications, thus should be a self_sufficent container
    '''

    def __init__(self):
        self.is_viewing = False
        self.data_queues = None
        self.record_tofile = True
        self.is_recording = False
        self.is_pulsing = False
        self.file_name = 'test.bin'
        self.recording_thread = None
        self.ai_ranges = None
        self.num_channels = None
        self.is_connected = False
        self.sampling_rate = 30
        self.log = logging.getLogger('DAQ-Board')
        self.log.setLevel(logging.DEBUG)
        self.devices = None
        self.daq_device = None
        self.board_num = 0
        self.timer_number = 0
        self.buffer_size_seconds = 2
        self.memhandle = None
        self.stop_recordingevent = None
        if OS_TYPE == 'Linux':
            self.scan_options = ScanOptions.CONTINUOUS
        elif OS_TYPE == 'Windows':
            self.scan_options = (ScanOptions.BACKGROUND | ScanOptions.CONTINUOUS |
                                 ScanOptions.SCALEDATA)

    def scan_devices(self) -> list:
        self.devices = get_daq_device_inventory(InterfaceType.USB)
        number_of_devices = len(self.devices)
        if number_of_devices == 0:
            self.log.error('No DAQ devices found')
            #raise RuntimeError('Error: No DAQ devices found')

        self.log.debug(f'Found {number_of_devices} DAQ device(s)')

        return [f"{self.devices[i].product_name}_{self.devices[i].unique_id}" for i in range(number_of_devices)]

    def connect_to_device(self, idx):
        if OS_TYPE == 'Linux':
            self.connect_to_device_linux(idx)
            self.log.debug('Connecting via Linux routine')
        elif OS_TYPE == 'Windows':
            self.connect_to_device_windows(idx)
            self.log.debug('Connecting via Windows routine')
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

        print('\nActive DAQ device: ', self.daq_device.product_name, ' (',
              self.daq_device.unique_id, ')\n', sep='')
        # self.daq_board_name = self.daq_device.product_name
        self.input_mode = AiInputMode.SINGLE_ENDED
        # set to differential mode
        a_input_mode(self.board_num, self.input_mode)
        # todo make an option for oter boards ?

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
        self.ai_info = ai_device.get_info()
        if not self.ai_info.has_pacer():
            raise RuntimeError('\nError: The specified DAQ device does not '
                               'support hardware paced analog input')

        ctr_device = self.daq_device.get_ctr_device()
        ctr_info = ctr_device.get_info()
        dev_num_counters = ctr_info.get_num_ctrs()
        self.log.info(f"This board has {dev_num_counters} counters")
        # Establish a connection to the DAQ device.
        descriptor = self.daq_device.get_descriptor()
        self.log.debug(f'Connecting to {descriptor.dev_string}')
        # For Ethernet devices using a connection_code other than the default
        # value of zero, change the line below to enter the desired code.
        self.daq_device.connect(connection_code=0)

        # The default input mode is SINGLE_ENDED.
        self.input_mode = AiInputMode.SINGLE_ENDED
        # If SINGLE_ENDED input mode is not supported, set to DIFFERENTIAL.
        if self.ai_info.get_num_chans_by_mode(AiInputMode.SINGLE_ENDED) <= 0:
            self.input_mode = AiInputMode.DIFFERENTIAL

        # Get the number of channels and validate the high channel number.
        self.num_channels = self.ai_info.get_num_chans_by_mode(self.input_mode)

        # Get a list of supported ranges and validate the range index.
        ranges = self.ai_info.get_ranges(self.input_mode)
        self.ai_ranges = [airange.name for airange in ranges]

        self.is_connected = True
        # Allocate a buffer to receive the data.
        # data = create_float_buffer(channel_count, samples_per_channel)

    def start_recording(self, settings: MCC_settings):
        # Record option is mandatory for now..
        self.low_chan, self.high_chan = settings.get_active_channels()
        self.ai_range = ULRange[settings.voltage_range]
        self.num_channels = settings.num_channels
        self.sampling_rate = settings.sampling_rate
        self.file_header = settings.to_header()

        # self.data_queues = [Queue(10000)] * self.num_channels
        self.data_queues = [Queue(1000) for _ in range(self.num_channels)]
        # self.stop_recordingevent = event
        Path("data").mkdir(exist_ok=True)
        try:
            self.file_name = Path("data") / f"{settings.session_name}.bin"
            if settings.session_name is None:
                raise AttributeError
        except AttributeError:  # no session name was passed
            self.file_name = Path("data") / f"DAQrec_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"

        if OS_TYPE == 'Linux':
            self.log.debug('Start recording via Linux routine')
            self.start_rec_time = time.monotonic()
            self.recording_thread = Thread(target=self.start_recording_linux)
            self.recording_thread.start()

        elif OS_TYPE == 'Windows':
            self.log.debug('Started recording-thread via Windows routine')
            self.start_rec_time = time.monotonic()
            self.recording_thread = Thread(target=self.start_recording_windows)
            self.recording_thread.start()
        else:
            raise NotImplementedError

        self.is_recording = True

    def stop_recording(self):
        self.log.info('Stopping recording')
        if OS_TYPE == 'Linux':
            try:
                self.daq_device.get_ai_device().scan_stop()
            except uldaq.ul_exception.ULException:
                self.log.warning("some UL exception occured")

        elif OS_TYPE == 'Windows':
            ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
        if self.is_pulsing:
            self.stop_pulsing()
        print(f"Stopping recording after {(time.monotonic() - self.start_rec_time):0.1f} s")
        self.recording_thread.join()
        # for queue in self.data_queues: # wait until the data showing is empty
        #    queue.join()
        self.is_recording = False
        self.is_viewing = False

    def start_recording_windows(self):
        # Create a circular buffer that can hold buffer_size_seconds worth of
        # data, or at least 10 points (this may need to be adjusted to prevent a buffer overrun)
        points_per_channel = max(self.sampling_rate * self.buffer_size_seconds, 10)

        # Some hardware requires that the total_count is an integer multiple
        # of the packet size. For this case, calculate a points_per_channel
        # that is equal to or just above the points_per_channel selected which matches that requirement.
        if self.ai_info.packet_size != 1:
            packet_size = self.ai_info.packet_size
            remainder = points_per_channel % packet_size
            if remainder != 0:
                points_per_channel += packet_size - remainder
        ul_buffer_count = points_per_channel * self.num_channels
        # When handling the buffer, we will read 1/10 of the buffer at a time
        write_chunk_size = int(ul_buffer_count / 20)

        self.memhandle = ul.scaled_win_buf_alloc(ul_buffer_count)

        # Allocate an array of doubles temporary storage of the data
        write_chunk_array = (c_double * write_chunk_size)()

        # Check if the buffer was successfully allocated
        if not self.memhandle:
            raise Exception('Failed to allocate memory')

        # Start the scan
        ul.a_in_scan(
            self.board_num, self.low_chan, self.high_chan, ul_buffer_count,
            self.sampling_rate, self.ai_range, self.memhandle, self.scan_options)

        status = Status.IDLE
        # Wait for the scan to start fully
        while status == Status.IDLE:
            status, _, _ = ul.get_status(self.board_num, FunctionType.AIFUNCTION)

        # Create a file for storing the data
        with open(self.file_name, 'wb') as fi:
            self.log.info(f'Writing data to {self.file_name}')
            head_len = len(self.file_header)
            fi.write(head_len.to_bytes(16, 'little'))
            fi.write(self.file_header)
            self.log.debug(f'written header')

            # Start the write loop
            prev_count = 0
            prev_index = 0
            write_ch_num = self.low_chan

            loop_counter = 0
            t = 0
            while status != Status.IDLE:
                # Get the latest counts
                t0 = time.monotonic()
                status, curr_count, _ = ul.get_status(self.board_num,
                                                      FunctionType.AIFUNCTION)
                new_data_count = curr_count - prev_count
                # Check for a buffer overrun before copying the data, so
                # that no attempts are made to copy more than a full buffer of data
                if new_data_count > ul_buffer_count:
                    # Print an error and stop writing
                    ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                    self.log.error('A buffer overrun occurred')
                    break

                # Check if a chunk is available
                if new_data_count > write_chunk_size:
                    wrote_chunk = True
                    # Copy the current data to a new array

                    # Check if the data wraps around the end of the UL buffer. Multiple copy operations will be
                    # required.
                    if prev_index + write_chunk_size > ul_buffer_count - 1:
                        first_chunk_size = ul_buffer_count - prev_index
                        second_chunk_size = (
                                write_chunk_size - first_chunk_size)

                        # Copy the first chunk of data to the write_chunk_array
                        ul.scaled_win_buf_to_array(
                            self.memhandle, write_chunk_array, prev_index,
                            first_chunk_size)

                        # Create a pointer to the location in write_chunk_array where we want to copy the remaining data
                        second_chunk_pointer = cast(addressof(write_chunk_array)
                                                    + first_chunk_size
                                                    * sizeof(c_double),
                                                    POINTER(c_double))

                        # Copy the second chunk of data to the write_chunk_array
                        ul.scaled_win_buf_to_array(
                            self.memhandle, second_chunk_pointer,
                            0, second_chunk_size)
                    else:
                        # Copy the data to the write_chunk_array
                        ul.scaled_win_buf_to_array(
                            self.memhandle, write_chunk_array, prev_index,
                            write_chunk_size)

                    # Check for a buffer overrun just after copying the data from the UL buffer. This will ensure
                    # that the data was not overwritten in the UL buffer before the copy was completed. This should
                    # be done before writing to the file, so that corrupt data does not end up in it.

                    status, curr_count, _ = ul.get_status(
                        self.board_num, FunctionType.AIFUNCTION)
                    if curr_count - prev_count > ul_buffer_count:
                        # Print an error and stop writing
                        ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                        self.log.error('A buffer overrun occurred2')
                        break

                    for i in range(write_chunk_size):
                        fi.write(bytearray(struct.pack("d", write_chunk_array[i])))
                        try:
                            self.data_queues[write_ch_num - self.low_chan].put_nowait(write_chunk_array[i])
                        except Full:
                            self.log.error('Queue buffer is FULL!!')
                            ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                            break
                        write_ch_num += 1
                        if write_ch_num == self.high_chan + 1:
                            write_ch_num = self.low_chan

                else:
                    wrote_chunk = False

                if wrote_chunk:
                    # Increment prev_count by the chunk size
                    prev_count += write_chunk_size
                    # Increment prev_index by the chunk size
                    prev_index += write_chunk_size
                    # Wrap prev_index to the size of the UL buffer
                    prev_index %= ul_buffer_count

                else:
                    # Wait a short amount of time for more data to be acquired.
                    time.sleep(0.0001)

                t += (time.monotonic() - t0)
                loop_counter += 1
                if loop_counter == 100:
                    loop_counter = 0
                    self.log.info(f'100 grabbing/rec loops took :{t:0.5f} s')
                    t = 0
        # free buffer before exiting the Thread
        ul.win_buf_free(self.memhandle)
        self.memhandle = None

    def start_recording_linux(self):
        ai_device = self.daq_device.get_ai_device()

        # Create a circular buffer that can hold buffer_size_seconds worth of
        # data, or at least 10 points (this may need to be adjusted to prevent
        # a buffer overrun)
        points_per_channel = max(self.sampling_rate * self.buffer_size_seconds, 10)

        # Some hardware requires that the total_count is an integer multiple
        # of the packet size. For this case, calculate a points_per_channel
        # that is equal to or just above the points_per_channel selected
        # which matches that requirement.
        # todo check if this is the case for our hardware ?
        # if self.ai_info.packet_size != 1:
        #    packet_size = self.ai_info.packet_size
        #    remainder = points_per_channel % packet_size
        #    if remainder != 0:
        #        points_per_channel += packet_size - remainder

        ul_buffer_count = points_per_channel * self.num_channels
        # When handling the buffer, we will read 1/10 of the buffer at a time
        write_chunk_size = int(ul_buffer_count / 20)

        self.memhandle = create_float_buffer(self.num_channels, points_per_channel)

        # Allocate an array of doubles temporary storage of the data
        write_chunk_array = (c_double * write_chunk_size)()

        # Check if the buffer was successfully allocated
        if not self.memhandle:
            raise Exception('Failed to allocate memory')

        # Start the scan
        rate = ai_device.a_in_scan(self.low_chan, self.high_chan, self.input_mode,
                                   self.ai_range, points_per_channel,
                                   self.sampling_rate, self.scan_options, AInScanFlag.DEFAULT, self.memhandle)
        self.log.info(f"Staring scanning with {rate} Hz")

        status = Status.IDLE
        # Wait for the scan to start fully
        while status == Status.IDLE:
            status, _ = ai_device.get_scan_status()

        # Create a file for storing the data
        with open(self.file_name, 'wb') as fi:
            self.log.info(f'Writing data to {self.file_name}')
            head_len = len(self.file_header)
            fi.write(head_len.to_bytes(16, 'little'))
            fi.write(self.file_header)
            self.log.debug(f'written header')

            # Start the write loop
            prev_count = 0
            prev_index = 0
            write_ch_num = self.low_chan

            loop_counter = 0
            t = 0
            while status != Status.IDLE:
                # Get the latest counts
                t0 = time.monotonic()

                status, transfer_status = ai_device.get_scan_status()
                curr_count = transfer_status.current_total_count
                curr_index = transfer_status.current_index  # indicates where are we in buffer ?

                new_data_count = curr_count - prev_count
                # Check for a buffer overrun before copying the data, so
                # that no attempts are made to copy more than a full buffer
                # of data
                if new_data_count > ul_buffer_count:
                    # Print an error and stop writing
                    if status == ScanStatus.RUNNING:
                        ai_device.scan_stop()
                    self.log.error('A buffer overrun occurred')
                    break

                # Check if a chunk is available
                if new_data_count > write_chunk_size:
                    wrote_chunk = True
                    # Copy the current data to a new array

                    # Check if the data wraps around the end of the UL
                    # buffer. Multiple copy operations will be required.
                    # in linux i could find out via transfer_status.current_index
                    if curr_index < prev_index - 1 and curr_index != 0:  # todo check if i need -1 ?
                        # self.log.info('This weird wrap happended.. ')
                        first_chunk_size = ul_buffer_count - prev_index
                        second_chunk_size = (
                                write_chunk_size - first_chunk_size)

                        # Copy the first chunk of data to the
                        # write_chunk_array

                        # write_chunk_array[:first_chunk_size] = np.frombuffer(self.memhandle, count=first_chunk_size, offset=8 * prev_index)
                        write_chunk_array[:first_chunk_size] = self.memhandle[prev_index:prev_index + first_chunk_size]

                        # Copy the second chunk of data to the
                        # write_chunk_array
                        # write_chunk_array[first_chunk_size:] = np.frombuffer(self.memhandle, count=curr_index, offset=0)
                        if second_chunk_size == 0:
                            pass
                        else:
                            write_chunk_array[:first_chunk_size] = self.memhandle[0:second_chunk_size]

                    else:
                        # write_chunk_array = np.copy(np.frombuffer(self.memhandle, count=write_chunk_size, offset=8 * prev_index))
                        # write_chunk_array = np.frombuffer(self.memhandle, count=write_chunk_size, offset=8 * prev_index)
                        write_chunk_array[:] = self.memhandle[prev_index:prev_index + write_chunk_size]

                        # potentially not, as long as i make sure the data was used before the buffer loops

                    # Check for a buffer overrun just after copying the data
                    # from the UL buffer. This will ensure that the data was
                    # not overwritten in the UL buffer before the copy was
                    # completed. This should be done before writing to the
                    # file, so that corrupt data does not end up in it.
                    status, transfer_status = ai_device.get_scan_status()
                    curr_count = transfer_status.current_total_count
                    if curr_count - prev_count > ul_buffer_count:
                        # Print an error and stop writing
                        if status == ScanStatus.RUNNING:
                            ai_device.scan_stop()
                        self.log.error('A buffer overrun occurred between copy ')
                        break

                    for i in range(write_chunk_size):
                        fi.write(bytearray(struct.pack("d", write_chunk_array[i])))
                        # f.write(str(write_chunk_array[i]) + ',')
                        try:
                            self.data_queues[write_ch_num - self.low_chan].put_nowait(write_chunk_array[i])
                            # todo consider doing this on client side !
                        except Full:
                            self.log.error('Queue buffer is FULL!!')
                            if status == ScanStatus.RUNNING:
                                ai_device.scan_stop()
                            break
                        write_ch_num += 1
                        if write_ch_num == self.high_chan + 1:
                            write_ch_num = self.low_chan
                            # f.write(u'\n')
                else:
                    wrote_chunk = False

                if wrote_chunk:
                    # Increment prev_count by the chunk size
                    prev_count += write_chunk_size
                    # Increment prev_index by the chunk size
                    prev_index += write_chunk_size
                    # Wrap prev_index to the size of the UL buffer
                    prev_index %= ul_buffer_count

                else:
                    # Wait a short amount of time for more data to be
                    # acquired.
                    time.sleep(0.0001)

                t += (time.monotonic() - t0)
                loop_counter += 1
                if loop_counter == 100:
                    loop_counter = 0
                    self.log.info(f'100 grabbing/rec loops took :{t:0.5f} s')
                    t = 0

        # free buffer before exiting the Thread
        self.memhandle = None

    def start_viewing(self, settings: MCC_settings):
        # Record option is mandatory for now..
        self.low_chan, self.high_chan = settings.get_active_channels()
        self.ai_range = ULRange[settings.voltage_range]
        self.num_channels = settings.num_channels
        self.sampling_rate = settings.sampling_rate
        self.data_queues = [Queue(1000) for _ in range(self.num_channels)]

        if OS_TYPE == 'Linux':
            self.log.debug('Start viewing via Linux routine')
            self.start_rec_time = time.monotonic()
            self.recording_thread = Thread(target=self.start_viewing_linux)
            self.recording_thread.start()

        elif OS_TYPE == 'Windows':
            raise NotImplementedError
            self.log.debug('Started recording-thread via Windows routine')
            # self.start_rec_time = time.monotonic()
            # self.recording_thread = Thread(target=self.start_recording_windows)
            # self.recording_thread.start()
        else:
            raise NotImplementedError

        self.is_viewing = True

    def start_viewing_linux(self):
        ai_device = self.daq_device.get_ai_device()
        # Create a circular buffer that can hold buffer_size_seconds worth of
        # data, or at least 10 points (this may need to be adjusted to prevent
        # a buffer overrun)
        points_per_channel = max(self.sampling_rate * self.buffer_size_seconds, 10)

        ul_buffer_count = points_per_channel * self.num_channels
        # When handling the buffer, we will read 1/10 of the buffer at a time
        write_chunk_size = int(ul_buffer_count / 20)

        self.memhandle = create_float_buffer(self.num_channels, points_per_channel)

        # Allocate an array of doubles temporary storage of the data
        write_chunk_array = (c_double * write_chunk_size)()

        # Check if the buffer was successfully allocated
        if not self.memhandle:
            raise Exception('Failed to allocate memory')

        # Start the scan
        rate = ai_device.a_in_scan(self.low_chan, self.high_chan, self.input_mode,
                                   self.ai_range, points_per_channel,
                                   self.sampling_rate, self.scan_options, AInScanFlag.DEFAULT, self.memhandle)
        self.log.info(f"Staring scanning with {rate} Hz")

        status = Status.IDLE
        # Wait for the scan to start fully
        while status == Status.IDLE:
            status, _ = ai_device.get_scan_status()

        # Start the write loop
        prev_count = 0
        prev_index = 0
        write_ch_num = self.low_chan

        loop_counter = 0
        t = 0
        while status != Status.IDLE:
            # Get the latest counts
            t0 = time.monotonic()

            status, transfer_status = ai_device.get_scan_status()
            curr_count = transfer_status.current_total_count
            curr_index = transfer_status.current_index  # indicates where are we in buffer ?

            new_data_count = curr_count - prev_count
            # Check for a buffer overrun before copying the data, so
            # that no attempts are made to copy more than a full buffer
            # of data
            if new_data_count > ul_buffer_count:
                # Print an error and stop writing
                if status == ScanStatus.RUNNING:
                    ai_device.scan_stop()
                self.log.error('A buffer overrun occurred')
                break

            # Check if a chunk is available
            if new_data_count > write_chunk_size:
                wrote_chunk = True
                # Copy the current data to a new array

                # Check if the data wraps around the end of the UL
                # buffer. Multiple copy operations will be required.
                # in linux i could find out via transfer_status.current_index
                if curr_index < prev_index - 1 and curr_index != 0:  # todo check if i need -1 ?
                    # self.log.info('This weird wrap happended.. ')
                    first_chunk_size = ul_buffer_count - prev_index
                    second_chunk_size = (
                            write_chunk_size - first_chunk_size)

                    # Copy the first chunk of data to the
                    # write_chunk_array

                    # write_chunk_array[:first_chunk_size] = np.frombuffer(self.memhandle, count=first_chunk_size, offset=8 * prev_index)
                    write_chunk_array[:first_chunk_size] = self.memhandle[prev_index:prev_index + first_chunk_size]

                    # Copy the second chunk of data to the
                    # write_chunk_array
                    # write_chunk_array[first_chunk_size:] = np.frombuffer(self.memhandle, count=curr_index, offset=0)
                    if second_chunk_size == 0:
                        # write_chunk_array[:] = self.memhandle[prev_index:prev_index + write_chunk_size]
                        pass
                    else:
                        try:
                            write_chunk_array[:first_chunk_size] = self.memhandle[0:second_chunk_size]
                        except ValueError:
                            print("a")


                else:
                    # write_chunk_array = np.copy(np.frombuffer(self.memhandle, count=write_chunk_size, offset=8 * prev_index))
                    # write_chunk_array = np.frombuffer(self.memhandle, count=write_chunk_size, offset=8 * prev_index)
                    write_chunk_array[:] = self.memhandle[prev_index:prev_index + write_chunk_size]

                    # potentially not, as long as i make sure the data was used before the buffer loops

                # Check for a buffer overrun just after copying the data
                # from the UL buffer. This will ensure that the data was
                # not overwritten in the UL buffer before the copy was
                # completed. This should be done before writing to the
                # file, so that corrupt data does not end up in it.
                status, transfer_status = ai_device.get_scan_status()
                curr_count = transfer_status.current_total_count
                if curr_count - prev_count > ul_buffer_count:
                    # Print an error and stop writing
                    if status == ScanStatus.RUNNING:
                        ai_device.scan_stop()
                    self.log.error('A buffer overrun occurred between copy ')
                    break

                for i in range(write_chunk_size):
                    try:
                        self.data_queues[write_ch_num - self.low_chan].put_nowait(write_chunk_array[i])
                        # todo consider doing this on client side !
                    except Full:
                        self.log.error('Queue buffer is FULL!!')
                        if status == ScanStatus.RUNNING:
                            ai_device.scan_stop()
                        break
                    write_ch_num += 1
                    if write_ch_num == self.high_chan + 1:
                        write_ch_num = self.low_chan
            else:
                wrote_chunk = False

            if wrote_chunk:
                # Increment prev_count by the chunk size
                prev_count += write_chunk_size
                # Increment prev_index by the chunk size
                prev_index += write_chunk_size
                # Wrap prev_index to the size of the UL buffer
                prev_index %= ul_buffer_count

            else:
                # Wait a short amount of time for more data to be
                # acquired.
                time.sleep(0.0001)

            t += (time.monotonic() - t0)
            loop_counter += 1
            if loop_counter == 100:
                loop_counter = 0
                self.log.info(f'100 grabbing/rec loops took :{t:0.5f} s')
                t = 0

        # free buffer before exiting the Thread
        self.memhandle = None

    def reset_counters(self):
        self.log.debug("Resetting counters")
        if OS_TYPE == 'Linux':
            self.reset_counters_linux()
        elif OS_TYPE == 'Windows':
            self.reset_counters_windows()

    def reset_counters_windows(self):
        """windows library routine to reset counters"""
        ctr_info = self.daq_device.get_ctr_info()
        self.dev_counters = []
        for idx in range(len(ctr_info)):
            counter_num = ctr_info.chan_info[0].channel_num
            self.dev_counters.append(counter_num)
            ul.c_clear(self.board_num, counter_num)

    def reset_counters_linux(self):
        """linux library routine to reset counters"""
        ctr_device = self.daq_device.get_ctr_device()
        ctr_info = ctr_device.get_info()
        dev_num_counters = ctr_info.get_num_ctrs()
        self.dev_counters = []
        for counter_number in range(dev_num_counters):
            ctr_device.c_clear(counter_number)
            self.dev_counters.append(counter_number)

    def get_single_counter(self) -> list:
        self.log.debug("Reading single value from counters")
        if OS_TYPE == 'Linux':
            return self.get_single_counter_linux()
        elif OS_TYPE == 'Windows':
            return self.get_single_counter_windows()

    def get_single_counter_linux(self) -> list:
        ctr_device = self.daq_device.get_ctr_device()
        counter_values = []
        for counter_num in self.dev_counters:
            counter_value = ctr_device.c_in(counter_num)
            counter_values.append(counter_value)
        return counter_values

    def get_single_counter_windows(self) -> list:
        counter_values = []
        for counter_num in self.dev_counters:
            counter_value = ul.c_in_32(self.board_num, counter_num)
            counter_values.append(counter_value)
        return counter_values

    def start_pulsing(self, freq: float = 30, duty_cycle: (float, None) = None):
        self.log.debug("Starting pulsing")
        pulse_width = 5  # ms
        if duty_cycle is None:
            duty_cycle = pulse_width / (1000 / freq)

        if OS_TYPE == 'Linux':
            self.start_pulsing_linux(freq, duty_cycle)
        elif OS_TYPE == 'Windows':
            self.start_pulsing_windows(freq, duty_cycle)
        self.is_pulsing = True
    def start_pulsing_windows(self, freq: float = 30, duty_cycle: (float, None) = 0.15):
        ctr_info = self.daq_device.get_ctr_info()

        # Find a pulse timer channel on the board
        first_chan = next((channel for channel in ctr_info.chan_info
                           if channel.type == CounterChannelType.CTRPULSE),
                          None)

        if not first_chan:
            self.log.error('Error: The DAQ device does not support pulse timers')

        self.timer_number, = first_chan.channel_num
        actual_frequency, actual_duty_cycle, _ = ul.pulse_out_start(
            self.board_num, self.timer_number, freq, duty_cycle)
        self.log.info(f"Start pulsing with {actual_frequency:0.1f} Hz and "
                      f"{actual_duty_cycle * (1000 / actual_frequency):0.3f} ms pulse width")

    def start_pulsing_linux(self, freq: float = 30, duty_cycle: (float, None) = 0.15):

        pulse_count = 0  # for continious operation
        initial_delay = 0

        tmr_device = self.daq_device.get_tmr_device()
        (actual_frequency,
         actual_duty_cycle,
         _) = tmr_device.pulse_out_start(self.timer_number, freq,
                                         duty_cycle, pulse_count,
                                         initial_delay, TmrIdleState.LOW,
                                         PulseOutOption.DEFAULT)

        self.log.info(f"Start pulsing with {actual_frequency:0.1f} Hz and "
                      f"{actual_duty_cycle * (1000 / actual_frequency):0.3f} ms pulse width")

    def stop_pulsing(self):
        self.log.debug("stopping pulsing")
        if OS_TYPE == 'Linux':
            tmr_device = self.daq_device.get_tmr_device()
            tmr_device.pulse_out_stop(self.timer_number)
        elif OS_TYPE == 'Windows':
            ul.pulse_out_stop(self.board_num, self.timer_number)
        self.is_pulsing = False

    def release_device(self):
        if OS_TYPE == 'Linux':
            if self.daq_device:
                self.stop_pulsing()
                self.daq_device.disconnect()
                self.daq_device.release()
        else:
            self.stop_pulsing()
            if self.memhandle:
                # Free the buffer in a finally block to prevent a memory leak.
                ul.win_buf_free(self.memhandle)
            ul.release_daq_device(self.board_num)
