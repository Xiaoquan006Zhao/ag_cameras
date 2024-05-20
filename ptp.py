from arena_api.system import system
from arena_api.buffer import BufferFactory
from arena_api.enums import PixelFormat
from arena_api.__future__.save import Writer
import time
import threading
import cv2
import ctypes
import numpy as np
import os

TAB1 = "  "
TAB2 = "    "
TAB3 = "      "
ERASE_LINE = "                            "

EXPOSURE_TIME = 10000.0
PTPSYNC_FRAME_RATE = 2.0
TIMEOUT = 20000
NUM_IMAGES = 5
pixel_format = PixelFormat.BGR8

def create_devices_with_tries():
    tries = 0
    tries_max = 6
    sleep_time_secs = 10
    while tries < tries_max:  # Wait for device for 60 seconds
        devices = system.create_device()
        if not devices:
            print(
                f'Try {tries+1} of {tries_max}: waiting for {sleep_time_secs} '
                f'secs for a device to be connected!')
            for sec_count in range(sleep_time_secs):
                time.sleep(1)
                print(f'{sec_count + 1} seconds passed ', '.' * sec_count, end='\r')
            tries += 1
        else:
            print(f'Created {len(devices)} device(s)')
            return devices
    else:
        raise Exception('No device found! Please connect a device and run the example again.')

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

def ptp_sync_cameras_and_acquire_images(system, devices):
    try:
        for i, device in enumerate(devices):
            print(f"{TAB3}ptp_sync_frame_rate: {get_node_value(device.nodemap, 'AcquisitionFrameRate')}")

            device_serial_number = get_node_value(device.nodemap, "DeviceSerialNumber")
            print(f"{TAB2}Prepare camera {device_serial_number}")

            # Manually set exposure time
            print(f"{TAB3}Exposure: ")
            set_node_value(device.nodemap, "ExposureAuto", "Off")
            set_node_value(device.nodemap, "ExposureTime", EXPOSURE_TIME)
            print(get_node_value(device.nodemap, "ExposureTime"))

            # Synchronize devices by enabling PTP
            print(f"{TAB3}PTP: ")
            set_node_value(device.nodemap, "PtpEnable", True)
            print("enabled" if get_node_value(device.nodemap, "PtpEnable") else "disabled")

            # Use max supported packet size. Use transfer control to ensure that only one camera is transmitting at a time.
            print(f"{TAB3}StreamAutoNegotiatePacketSize: ")
            set_node_value(device.tl_stream_nodemap, "StreamAutoNegotiatePacketSize", True)
            print(get_node_value(device.tl_stream_nodemap, "StreamAutoNegotiatePacketSize"))

            # Enable stream packet resend
            print(f"{TAB3}StreamPacketResendEnable: ")
            set_node_value(device.tl_stream_nodemap, "StreamPacketResendEnable", True)
            print(get_node_value(device.tl_stream_nodemap, "StreamPacketResendEnable"))

            # Set acquisition mode to 'Continuous'
            print(f"{TAB3}Set acquisition mode to 'Continuous'")
            set_node_value(device.nodemap, "AcquisitionMode", "Continuous")

            # Set acquisition start mode to 'PTPSync'
            print(f"{TAB3}Set acquisition start mode to 'PTPSync'")
            set_node_value(device.nodemap, "AcquisitionStartMode", "PTPSync")

            # Set StreamBufferHandlingMode to 'NewestOnly'
            print(f"{TAB3}Set StreamBufferHandlingMode to 'NewestOnly'")
            set_node_value(device.tl_stream_nodemap, "StreamBufferHandlingMode", "NewestOnly")

            set_node_value(device.nodemap, "PixelFormat", "BGR8")
            print(f"{TAB3}Set pixel format to 'BGR8'")

            # Set Packet Delay and Transmission Delay based on device index
            packet_delay = 240000
            # packet_delay = 160000
            transmission_delay = 0 if i == 0 else 80000 * i
            set_node_value(device.nodemap, "GevSCPD", packet_delay)
            print(f"{TAB3}GevSCPD: {get_node_value(device.nodemap, 'GevSCPD')}")
            set_node_value(device.nodemap, "GevSCFTD", transmission_delay)
            print(f"{TAB3}GevSCFTD: {get_node_value(device.nodemap, 'GevSCFTD')}")

            # Frame rate
            print(f"{TAB3}ptp_sync_frame_rate: {get_node_value(device.nodemap, 'AcquisitionFrameRate')}")
            acquisition_frame_rate = device.nodemap.get_node("AcquisitionFrameRate")
            acquisition_frame_rate.value = acquisition_frame_rate.max
            print(f"{TAB3}acquisition_frame_rate: {get_node_value(device.nodemap, 'AcquisitionFrameRate')}")

            # PTPSyncFrameRate
            print(f"{TAB3}ptp_sync_frame_rate: {get_node_value(device.nodemap, 'PTPSyncFrameRate')}")
            ptp_sync_frame_rate = device.nodemap.get_node("PTPSyncFrameRate")
            ptp_sync_frame_rate.value = 5.0
            print(f"{TAB3}ptp_sync_frame_rate: {get_node_value(device.nodemap, 'PTPSyncFrameRate')}")

            time.sleep(1)
            print(f"{TAB3}acquisition_frame_rate: {get_node_value(device.nodemap, 'AcquisitionFrameRate')}")


        # Prepare system
        print(f"{TAB2}Prepare system")

        # Wait for devices to negotiate their PTP relationship
        print(f"{TAB1}Wait for devices to negotiate. This can take up to about 40s.")
        i = 0
        while True:
            master_found = False
            restart_sync_check = False

            for device in devices:
                ptp_status = get_node_value(device.nodemap, "PtpStatus")
                if ptp_status == "Master":
                    if master_found:
                        restart_sync_check = True
                        break
                    master_found = True
                elif ptp_status != "Slave":
                    restart_sync_check = True
                    break

            if not restart_sync_check and master_found:
                break

            time.sleep(1)

            if i % 10 == 0:
                print(f"\r{ERASE_LINE}\r{TAB2}", end="", flush=True)

            print(".", end="", flush=True)
            i += 1

        # Start stream
        print(f"\n{TAB1}Start stream")
        for device in devices:
            device.start_stream()

        buffer = None

        # Get images and check timestamps
        print(f"{TAB1}Get images")
        for i in range(NUM_IMAGES):
            for j, device in enumerate(devices):
                try:
                    device_serial_number = get_node_value(device.nodemap, "DeviceSerialNumber")
                    print(f"{TAB2}Image {i} from device {device_serial_number}")

                    print(1)
                    buffer = device.get_buffer()

                    converted = BufferFactory.convert(buffer, pixel_format)
                    writer = Writer()
                    writer.pattern = f'images/{device_serial_number}/image_{i}.jpg'
                    writer.save(converted)
                    BufferFactory.destroy(converted)
                    device.requeue_buffer(buffer)
                except Exception as e:
                    print(f"Error acquiring image {i} from device {device_serial_number}: {e}")

        # Stop stream
        print(f"{TAB1}Stop stream")
        for device in devices:
            device.stop_stream()

    except Exception as e:
        print(e)
        print(f"An error occurred during PTP sync and image acquisition: {e}")

def main():
    try:
        devices = create_devices_with_tries()
        # Run example
        print("Commence example\n")
        ptp_sync_cameras_and_acquire_images(system, devices)
        print("\nExample complete\n")

        # Clean up example
        for device in devices:
            system.destroy_device(device)
    except Exception as e:
        print(f"An error occurred in the main function: {e}")

if __name__ == "__main__":
    main()
