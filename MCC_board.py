from __future__ import absolute_import, division, print_function
from builtins import *  # @UnusedWildImport
from time import sleep
from ctypes import cast, POINTER, c_double, c_ushort, c_ulong ,addressof, sizeof

from mcculw import ul
from mcculw.device_info import DaqDeviceInfo
from mcculw.enums import ULRange,ScanOptions, FunctionType, Status
from mcculw.ul import ULError

from mcc_utils import config_first_detected_device


class MCCBoard:
    '''Class for acquiring data from a MCC board on a host computer.'''
    def __init__(self,board_num=0,sampling_rate = 100):
        self.ai_info = None
        self.dio_info = None
        self.sampling_rate = sampling_rate # Hz

        self.board_num = board_num
        self.dev_id_list = [276]
        self.ai_range = ULRange.BIP10VOLTS
        self.connected = False

        self.memhandle = None
        self.data_file = None
        self.running = False
        self.file_type = None

    def connect(self):
        try:
            config_first_detected_device(self.board_num, self.dev_id_list)
            daq_dev_info = DaqDeviceInfo(self.board_num)
            if not daq_dev_info.supports_analog_input:
                raise Exception('Error: The DAQ device does not support '
                                'analog input')
            if not daq_dev_info.supports_digital_io:
                raise Exception('Error: The DAQ device does not support '
                                'digital I/O')
            if not daq_dev_info.supports_analog_output:
                print('The DAQ device does not support analog output')
            if not daq_dev_info.supports_counters:
                print('The DAQ device does not support counters')

            print('\nActive DAQ device: ', daq_dev_info.product_name, ' (',
                  daq_dev_info.unique_id, ')\n', sep='')
            self.ai_info = daq_dev_info.get_ai_info()
            self.dio_info = daq_dev_info.get_dio_info()

            if self.ai_range not in self.ai_info.supported_ranges:
                print('Unsupported AI Range!!!')

            print('{:d} AI channels available'.format(self.ai_info.num_chans))
            print('{:d} DIO channels available'.format(self.dio_info.num_ports))
            print("____________________________________")
            self.connected = True
        except ULError as e:
            # Display the error
            print("A UL error occurred. Code: " + str(e.errorcode)
                  + " Message: " + e.message)

    def read_singlevalue(self,channel=0):
        try:
            if self.ai_info.resolution <= 16:
                # Use the a_in method for devices with a resolution <= 16
                value = ul.a_in(self.board_num, channel, self.ai_range)
                v_value = ul.v_in(self.board_num, channel, self.ai_range)
                # Convert the raw value to engineering units
                eng_units_value = ul.to_eng_units(self.board_num, self.ai_range, value)
            else:
                # Use the a_in_32 method for devices with a resolution > 16
                # (optional parameter omitted)
                value = ul.a_in_32(self.board_num, channel, self.ai_range)
                # Convert the raw value to engineering units
                eng_units_value = ul.to_eng_units_32(self.board_num, self.ai_range, value)

            # Display the raw value
            print('Raw Value:', value)
            # Display the engineering value
            print('Engineering Value: {:.3f}'.format(eng_units_value))
            print('Voltage: {:.3f}'.format(v_value))

        except Exception as e:
            print('\n', e)

    def read_multiplevalue(self, points_per_channel = 1000):
        low_chan = 0
        high_chan = 7
        num_chans = high_chan - low_chan + 1
        try:
             # read all channels
            total_count = points_per_channel * num_chans   #data size
            scan_options = ScanOptions.FOREGROUND
            if ScanOptions.SCALEDATA in self.ai_info.supported_scan_options:
                # If the hardware supports the SCALEDATA option, it is easiest to use it.
                # this is available for USB-204 !!
                scan_options |= ScanOptions.SCALEDATA
                self.memhandle = ul.scaled_win_buf_alloc(total_count)  # Convert the memhandle to a ctypes array.
                # Use the memhandle_as_ctypes_array_scaled method for scaled buffers.
                ctypes_array = cast(self.memhandle, POINTER(c_double))
            elif self.ai_info.resolution <= 16:
                # Use the win_buf_alloc method for devices with a resolution <= 16
                self.memhandle = ul.win_buf_alloc(total_count)   # Convert the memhandle to a ctypes array.
                # Use the memhandle_as_ctypes_array method for devices with a resolution <= 16.
                ctypes_array = cast(self.memhandle, POINTER(c_ushort))
            else:
                # Use the win_buf_alloc_32 method for devices with a resolution > 16
                self.memhandle = ul.win_buf_alloc_32(total_count)    # Convert the memhandle to a ctypes array.
                # Use the memhandle_as_ctypes_array_32 method for devices with a  resolution > 16
                ctypes_array = cast(self.memhandle, POINTER(c_ulong))
            # Note: the ctypes array will no longer be valid after win_buf_free is called.
            # A copy of the buffer can be created using win_buf_to_array or
            # win_buf_to_array_32 before the memory is freed. The copy can be used at any time.

            # Check if the buffer was successfully allocated
            if not self.memhandle:
                raise Exception('Error: Failed to allocate memory')

            # Start the scan
            ul.a_in_scan(
                self.board_num, low_chan, high_chan, total_count,
                self.sampling_rate, self.ai_range, self.memhandle, scan_options)

            print('Scan completed successfully. Data:')

            # Create a format string that aligns the data in columns
            row_format = '{:>5}' + '{:>10}' * num_chans

            # Print the channel name headers
            labels = ['Index']
            for ch_num in range(low_chan, high_chan + 1):
                labels.append('CH' + str(ch_num))
            print(row_format.format(*labels))

            # Print the data
            data_index = 0
            for index in range(points_per_channel):
                display_data = [index]
                for _ in range(num_chans):
                    if ScanOptions.SCALEDATA in scan_options:
                        # If the SCALEDATA ScanOption was used, the values
                        # in the array are already in engineering units.
                        eng_value = ctypes_array[data_index]
                    else:
                        # If the SCALEDATA ScanOption was NOT used, the
                        # values in the array must be converted to
                        # engineering units using ul.to_eng_units().
                        eng_value = ul.to_eng_units(
                            self.board_num, self.ai_range, ctypes_array[data_index])
                    data_index += 1
                    display_data.append('{:.3f}'.format(eng_value))
                # Print this row
                print(row_format.format(*display_data))

        except Exception as e:
            print('\n', e)
        finally:
            if self.memhandle:
                # Free the buffer in a finally block to prevent a memory leak.
                ul.win_buf_free(self.memhandle)
                self.memhandle = None

    def record_infile(self):
        low_chan = 0
        high_chan = 3
        num_chans = high_chan - low_chan + 1
        file_name = 'scan_data.csv'

        # The size of the UL buffer to create, in seconds
        buffer_size_seconds = 2
        # The number of buffers to write. After this number of UL buffers are written to file,
        # the example will be stopped.
        num_buffers_to_write = 5
        try:
            # Create a circular buffer that can hold buffer_size_seconds worth of
            # data, or at least 10 points (this may need to be adjusted to prevent
            # a buffer overrun)
            points_per_channel = max(self.sampling_rate * buffer_size_seconds, 10)

            # Some hardware requires that the total_count is an integer multiple
            # of the packet size. For this case, calculate a points_per_channel
            # that is equal to or just above the points_per_channel selected which matches that requirement.
            if self.ai_info.packet_size != 1:
                packet_size = self.ai_info.packet_size
                remainder = points_per_channel % packet_size
                if remainder != 0:
                    points_per_channel += packet_size - remainder

            ul_buffer_count = points_per_channel * num_chans
            # Write the UL buffer to the file num_buffers_to_write times.
            points_to_write = ul_buffer_count * num_buffers_to_write
            # When handling the buffer, we will read 1/10 of the buffer at a time
            write_chunk_size = int(ul_buffer_count / 10)

            scan_options = (ScanOptions.BACKGROUND | ScanOptions.CONTINUOUS |
                            ScanOptions.SCALEDATA)

            self.memhandle = ul.scaled_win_buf_alloc(ul_buffer_count)

            # Allocate an array of doubles temporary storage of the data
            write_chunk_array = (c_double * write_chunk_size)()

            # Check if the buffer was successfully allocated
            if not self.memhandle:
                raise Exception('Failed to allocate memory')

            # Start the scan
            ul.a_in_scan(
                self.board_num, low_chan, high_chan, ul_buffer_count,
                self.sampling_rate, self.ai_range, self.memhandle, scan_options)

            status = Status.IDLE
            # Wait for the scan to start fully
            while status == Status.IDLE:
                status, _, _ = ul.get_status(self.board_num, FunctionType.AIFUNCTION)

            # Create a file for storing the data
            with open(file_name, 'w') as f:
                print('Writing data to ' + file_name, end='')

                # Write a header to the file
                for chan_num in range(low_chan, high_chan + 1):
                    f.write('Channel ' + str(chan_num) + ',')
                f.write(u'\n')

                # Start the write loop
                prev_count = 0
                prev_index = 0
                write_ch_num = low_chan
                while status != Status.IDLE:
                    # Get the latest counts
                    status, curr_count, _ = ul.get_status(self.board_num,
                                                          FunctionType.AIFUNCTION)

                    new_data_count = curr_count - prev_count

                    # Check for a buffer overrun before copying the data, so
                    # that no attempts are made to copy more than a full buffer
                    # of data
                    if new_data_count > ul_buffer_count:
                        # Print an error and stop writing
                        ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                        print('A buffer overrun occurred')
                        break

                    # Check if a chunk is available
                    if new_data_count > write_chunk_size:
                        wrote_chunk = True
                        # Copy the current data to a new array

                        # Check if the data wraps around the end of the UL
                        # buffer. Multiple copy operations will be required.
                        if prev_index + write_chunk_size > ul_buffer_count - 1:
                            first_chunk_size = ul_buffer_count - prev_index
                            second_chunk_size = (
                                    write_chunk_size - first_chunk_size)

                            # Copy the first chunk of data to the
                            # write_chunk_array
                            ul.scaled_win_buf_to_array(
                                self.memhandle, write_chunk_array, prev_index,
                                first_chunk_size)

                            # Create a pointer to the location in
                            # write_chunk_array where we want to copy the
                            # remaining data
                            second_chunk_pointer = cast(addressof(write_chunk_array)
                                                        + first_chunk_size
                                                        * sizeof(c_double),
                                                        POINTER(c_double))

                            # Copy the second chunk of data to the
                            # write_chunk_array
                            ul.scaled_win_buf_to_array(
                                self.memhandle, second_chunk_pointer,
                                0, second_chunk_size)
                        else:
                            # Copy the data to the write_chunk_array
                            ul.scaled_win_buf_to_array(
                                self.memhandle, write_chunk_array, prev_index,
                                write_chunk_size)

                        # Check for a buffer overrun just after copying the data
                        # from the UL buffer. This will ensure that the data was
                        # not overwritten in the UL buffer before the copy was
                        # completed. This should be done before writing to the
                        # file, so that corrupt data does not end up in it.
                        status, curr_count, _ = ul.get_status(
                            self.board_num, FunctionType.AIFUNCTION)
                        if curr_count - prev_count > ul_buffer_count:
                            # Print an error and stop writing
                            ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
                            print('A buffer overrun occurred')
                            break

                        for i in range(write_chunk_size):
                            f.write(str(write_chunk_array[i]) + ',')
                            write_ch_num += 1
                            if write_ch_num == high_chan + 1:
                                write_ch_num = low_chan
                                f.write(u'\n')
                    else:
                        wrote_chunk = False

                    if wrote_chunk:
                        # Increment prev_count by the chunk size
                        prev_count += write_chunk_size
                        # Increment prev_index by the chunk size
                        prev_index += write_chunk_size
                        # Wrap prev_index to the size of the UL buffer
                        prev_index %= ul_buffer_count

                        if prev_count >= points_to_write:
                            break
                        print('.', end='')
                    else:
                        # Wait a short amount of time for more data to be
                        # acquired.
                        sleep(0.1)

            ul.stop_background(self.board_num, FunctionType.AIFUNCTION)
        except Exception as e:
            print('\n', e)
        finally:
            if self.memhandle:
                # Free the buffer in a finally block to prevent a memory leak.
                ul.win_buf_free(self.memhandle)
                self.memhandle = None

    def disconnect(self):
        ul.release_daq_device(self.board_num)
        self.connected = False
        if self.memhandle:
            # Free the buffer in a finally block to prevent a memory leak.
            ul.win_buf_free(self.memhandle)



