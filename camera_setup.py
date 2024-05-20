import threading
import time
import queue
import ctypes
import numpy as np
import cv2
import os

from arena_api.system import system
from arena_api.buffer import BufferFactory
from arena_api.__future__.save import Writer
from multiprocessing import Value
import json

width1 = 2048
height1 = 1536


def set_node_value(nodemap, node, value):
    node_obj = nodemap.get_node(node)
    if node_obj is not None:
        node_obj.value = value
    else:
        print(f"Node {node} not found")


def get_node_value(nodemap, node):
    node_obj = nodemap.get_node(node)
    if node_obj is not None:
        return node_obj.value
    else:
        print(f"Node {node} not found")
        return None


def create_devices_with_tries():
    with threading.Lock():
        tries = 0
        tries_max = 6
        sleep_time_secs = 10
        while tries < tries_max:
            devices = system.create_device()
            if not devices:
                safe_print(
                    f"Try {tries+1} of {tries_max}: waiting for {sleep_time_secs} "
                    f"secs for a device to be connected!"
                )
                for sec_count in range(sleep_time_secs):
                    time.sleep(1)
                    safe_print(f"{sec_count + 1 } seconds passed ", "." * sec_count, end="\r")
                tries += 1
            else:
                safe_print(f"Created {len(devices)} device(s)")
                return devices
        else:
            raise Exception(f"No device found! Please connect a device and run " f"the example again.")


def Camera_On(Set_exposure, which_camera, device, threading_event, threading_condition):
    class Video_Capture:
        def __init__(self, Set_exposure, which_camera, device, threading_event, threading_condition):
            self.frame_holder = None
            self.device = device
            self.which_camera = which_camera
            self.threading_event = threading_event
            self.threading_condition = threading_condition
            self.working_properly = False
            self.num_channels = 3
            self.setup(Set_exposure)

        # Start stream in a separate thread
        def startProcess(self):
            t = threading.Thread(target=self.start_stream, args=())
            t.daemon = True
            t.start()

        def setup(self, Set_exposure):
            nodemap = self.device.nodemap
            device_serial_number = get_node_value(device.nodemap, "DeviceSerialNumber")

            # Manually set exposure time
            set_node_value(device.nodemap, "ExposureAuto", "Off")
            set_node_value(device.nodemap, "ExposureTime", Set_exposure)

            # Synchronize devices by enabling PTP
            set_node_value(device.nodemap, "PtpEnable", True)

            # Use max supported packet size. Use transfer control to ensure that only one camera
            # is transmitting at a time.
            set_node_value(device.tl_stream_nodemap, "StreamAutoNegotiatePacketSize", True)
            set_node_value(device.tl_stream_nodemap, "StreamPacketResendEnable", True)
            set_node_value(device.nodemap, "AcquisitionMode", "Continuous")
            set_node_value(device.nodemap, "AcquisitionStartMode", "PTPSync")
            set_node_value(device.tl_stream_nodemap, "StreamBufferHandlingMode", "NewestOnly")
            set_node_value(device.nodemap, "PixelFormat", "BGR8")

            # Set Packet Delay and Transmission Delay based on device index
            i = self.which_camera
            packet_delay = 240000
            transmission_delay = 0 if i == 0 else 80000 * i
            set_node_value(device.nodemap, "GevSCPD", packet_delay)
            set_node_value(device.nodemap, "GevSCFTD", transmission_delay)

            # Eanble Max Frame rate
            acquisition_frame_rate = device.nodemap.get_node("AcquisitionFrameRate")
            acquisition_frame_rate.value = acquisition_frame_rate.max
            print(f"acquisition_frame_rate: {get_node_value(device.nodemap, 'AcquisitionFrameRate')}")

            # PTPSyncFrameRate (for some cameras, this node may not be available)
            # print(f"{TAB3}ptp_sync_frame_rate: {get_node_value(device.nodemap, 'PTPSyncFrameRate')}")
            # ptp_sync_frame_rate = device.nodemap.get_node("PTPSyncFrameRate")
            # ptp_sync_frame_rate.value = 5.0

            return self.num_channels

        def start_stream(self):
            safe_print(f"Camera_{self.which_camera} starts streaming.")

            with self.device.start_stream():
                self.working_properly = True

                # Continuously get buffer
                while True:
                    with threading.Lock():
                        safe_print(self.threading_event)
                        buffer = self.device.get_buffer()

                        # Convert buffer data to a numpy array
                        item = BufferFactory.copy(buffer)
                        buffer_bytes_per_pixel = int(len(item.data) / (item.width * item.height))
                        array = (ctypes.c_ubyte * self.num_channels * item.width * item.height).from_address(
                            ctypes.addressof(item.pbytes)
                        )
                        npndarray = np.ndarray(
                            buffer=array, dtype=np.uint8, shape=(item.height, item.width, buffer_bytes_per_pixel)
                        )

                        # Save the buffer to the holder
                        self.frame_holder = (npndarray, self.which_camera)

                        # Notify the main app that this camera has finished pushing buffer
                        self.threading_event.set()

                    # Wait for other cameras to finish pushing buffer
                    with self.threading_condition:
                        safe_print(f"Camera_{self.which_camera} finished pushing buffer. Waiting for other Cameras.")

                        # Waiting for main app to receive all buffers and successfully display them
                        self.threading_condition.wait()

                    # Reset the memory usgae of the buffer
                    BufferFactory.destroy(item)
                    self.device.requeue_buffer(buffer)

        def read(self):
            return self.frame_holder

        def stop_stream(self):
            if self.working_properly:
                self.device.stop_stream()
                self.device.nodemap["UserSetSelector"].value = "Default"
                self.device.nodemap["UserSetLoad"].execute()

                print(f"Shutting camera_{self.which_camera}")

    frame0 = Video_Capture(Set_exposure, which_camera, device, threading_event, threading_condition)
    return frame0


def Camera_off(frame):
    frame.stop_stream()


def safe_print(*args, **kwargs):
    with threading.Lock():
        print(*args, **kwargs)
