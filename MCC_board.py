from __future__ import absolute_import, division, print_function
from builtins import *  # @UnusedWildImport
from time import sleep
import datetime 

from ctypes import cast, POINTER, c_double, c_ushort, c_ulong ,addressof, sizeof

from mcculw import ul
from mcculw.device_info import DaqDeviceInfo
from mcculw.enums import ULRange,ScanOptions, FunctionType, Status
from mcculw.ul import ULError

from mcc_utils import config_first_detected_device

class RecordingConfig:
    def __init__(self):
        self.session_name = "TestSession"
        self.subject = "MusterSubject"
        self.session_path = ''
        self.VERSION = 0.1
        self.sampling_rate = 100 
        self.board_num = 0
        self.dev_id_list = [276]
        
#TODO find out sizes which are returned from the background process
#TODO test writing/reading to a binary datafile 


class MCCBoard:
    '''Class for acquiring data from a MCC board on a host computer.
    This class may be reused in different gui applications, thus should be a self_sufficent container    
    '''
    def __init__(self,cfg,file_type='csv'):
        
        self.cfg = cfg # this shall receive a cfg dict with all the variables.. which are read by GUI from a config file.        
        self.data_temp = './' # here we temporally record the data, afterwards it could be moved to corresponding server ? Abstract the move to GUI
        
        self.sampling_rate = self.cfg.sampling_rate # Hz
        self.board_num = self.cfg.board_num
        self.dev_id_list = self.cfg.dev_id_list
        self.file_type = file_type
        
        self.ai_range = ULRange.BIP10VOLTS
        self.connected = False

        self.memhandle = None        
        self.ai_info = None
        self.dio_info = None
        
        self.data_file = None
        self.running = False
        

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
            self.cfg.daq_device = daq_dev_info.product_name
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
        """
        Just a short test fucntion to be deleted later
        """
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
        """
        Just a short test fucntion to be deleted later
        """
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
        """
        test function records a predefined length of samples into a file
        """
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
        self.stop_recording() # just in case
        ul.release_daq_device(self.board_num)
        self.connected = False        
        if self.memhandle:
            # Free the buffer in a finally block to prevent a memory leak.
            ul.win_buf_free(self.memhandle)
    
    def start_recording(self):        
        '''Open data file and write data header.'''
        assert self.file_type in ['csv', 'ppd'], 'Invalid file type'
        #self.file_type = file_type
        date_time = datetime.now()
        file_name = subject_ID + date_time.strftime('-%Y-%m-%d-%H%M%S') + '.' + file_type
        file_path = os.path.join(self.data_dir, file_name)
        header_dict = {'subject_ID': self.cfg.subject,
                       'session': self.cfg.session_name,
                       'date_time' : date_time.isoformat(timespec='seconds'),
                       'daq_device': self.cfg.daq_device,
                       'sampling_rate': self.sampling_rate,                       
                       'version': self.cfg.VERSION}
        #TODO add info about channels we r recording!
        #Check the other config i had maybe can be reused !
        if file_type == 'ppd': # Single binary .ppd file.
            self.data_file = open(file_path, 'wb')
            data_header = json.dumps(header_dict).encode()
            self.data_file.write(len(data_header).to_bytes(2, 'little'))
            self.data_file.write(data_header)
        elif file_type == 'csv': # Header in .json file and data in .csv file.
            with open(os.path.join(data_dir, file_name[:-4] + '.json'), 'w') as headerfile:
                headerfile.write(json.dumps(header_dict, sort_keys=True, indent=4))
            self.data_file = open(file_path, 'w')
            self.data_file.write('Analog1, Analog2, Digital1, Digital2\n')
        return file_name
        
    def stop_recording(self):
        if self.data_file:
            self.data_file.close()
        self.data_file = None
    
    def grab_and_dump(self):
        """
        here i grab a piece of data write it to file and return it to the caller
        - should be analogous to process_data() of acquisition_board
        so far only copied not run or tested 
        
        only dump if recording was started, otherwise just return values for display
        """
       
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
                if self.data_file:
                    for i in range(write_chunk_size):
                        self.data_file.write(str(write_chunk_array[i]) + ',')
                        write_ch_num += 1
                        if write_ch_num == high_chan + 1:
                            write_ch_num = low_chan
                            self.data_file.write(u'\n')
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
                sleep(0.1)
    

