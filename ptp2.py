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
PTPSYNC_FRAME_RATE = 7.0
TIMEOUT = 20000
NUM_IMAGES = 5
pixel_format = PixelFormat.BGR8

# Node interaction functions
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

def execute_node(nodemap, node):
    node_obj = nodemap.get_node(node)
    if node_obj is not None:
        node_obj.execute()
    else:
        print(f"Node {node} not found")

# Device creation
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

# Main script
def main():
    devices = create_devices_with_tries()
    
    if len(devices) < 2:
        raise Exception('At least two cameras are required for PTP synchronization')

    master_cam = devices[0]
    slave_cams = devices[1:]

    master_nodemap = master_cam.nodemap
    slave_nodemaps = [cam.nodemap for cam in slave_cams]

    # Step 1: Enable PTP
    set_node_value(master_nodemap, "PtpEnable", True)
    for nodemap in slave_nodemaps:
        set_node_value(nodemap, "PtpEnable", True)

    # Step 2: Set one camera as the master
    set_node_value(master_nodemap, "PtpSlaveOnly", False)
    while get_node_value(master_nodemap, "PtpStatus") != "Master":
        time.sleep(0.1)

    # Step 3: Set the remaining cameras as slaves
    for nodemap in slave_nodemaps:
        set_node_value(nodemap, "PtpSlaveOnly", True)
        while get_node_value(nodemap, "PtpStatus") != "Slave":
            time.sleep(0.1)

    # Step 4: Set TransferControlMode to UserControlled
    set_node_value(master_nodemap, "TransferControlMode", "UserControlled")
    set_node_value(master_nodemap, "TransferOperationMode", "Continuous")
    execute_node(master_nodemap, "TransferStop")
    for nodemap in slave_nodemaps:
        set_node_value(nodemap, "TransferControlMode", "UserControlled")
        set_node_value(nodemap, "TransferOperationMode", "Continuous")
        execute_node(nodemap, "TransferStop")

    # Step 5: Enable Trigger Mode
    set_node_value(master_nodemap, "TriggerMode", "On")
    set_node_value(master_nodemap, "TriggerSelector", "FrameStart")
    set_node_value(master_nodemap, "TriggerSource", "Action0")
    for nodemap in slave_nodemaps:
        set_node_value(nodemap, "TriggerMode", "On")
        set_node_value(nodemap, "TriggerSelector", "FrameStart")
        set_node_value(nodemap, "TriggerSource", "Action0")

    # Step 6: Settings for Scheduled Action Command
    action_device_key = 1  # Example device key
    action_group_key = 1  # Example group key
    action_group_mask = 1  # Example group mask

    set_node_value(master_nodemap, "ActionUnconditionalMode", "On")
    set_node_value(master_nodemap, "ActionSelector", 0)
    set_node_value(master_nodemap, "ActionDeviceKey", action_device_key)
    set_node_value(master_nodemap, "ActionGroupKey", action_group_key)
    set_node_value(master_nodemap, "ActionGroupMask", action_group_mask)
    for nodemap in slave_nodemaps:
        set_node_value(nodemap, "ActionUnconditionalMode", "On")
        set_node_value(nodemap, "ActionSelector", 0)
        set_node_value(nodemap, "ActionDeviceKey", action_device_key)
        set_node_value(nodemap, "ActionGroupKey", action_group_key)
        set_node_value(nodemap, "ActionGroupMask", action_group_mask)

    # Step 7: Firing Scheduled Action Command
    execute_node(master_nodemap, "PtpDataSetLatch")
    curr_ptp = get_node_value(master_nodemap, "PtpDataSetLatchValue")
    action_delta_time = 1  # Example action delta time in seconds
    round_up_action_time = True

    if round_up_action_time:
        curr_ptp = (curr_ptp // 1000000000 + action_delta_time + 1) * 1000000000
    else:
        curr_ptp += action_delta_time * 1000000000

    print(f'Scheduled Action Command set for time: {curr_ptp} ns')
    set_node_value(system.tl_system_nodemap, "ActionCommandExecuteTime", curr_ptp)
    execute_node(system.tl_system_nodemap, "ActionCommandFireCommand")

    print(f"\n{TAB1}Start stream")
    for device in devices:
        device.start_stream()

    # Step 8: Transfer grabbed images to the host
    for cam in devices:
        nodemap = cam.nodemap
        execute_node(nodemap, "TransferStart")
        image = cam.get_buffer()
        execute_node(nodemap, "TransferStop")
        if image:
            print(f"Image from {cam} received")
            # Add code to handle the received image, e.g., saving or processing

if __name__ == "__main__":
    main()
