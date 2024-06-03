from arena_api.system import system
import threading
import time


def safe_print(*args, **kwargs):
    with threading.Lock():
        print(*args, **kwargs)


def create_devices_with_tries():
    with threading.Lock():
        tries = 0
        tries_max = 6
        sleep_time_secs = 10
        while tries < tries_max:
            devices = system.create_device()
            print(len(devices))
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


devices = create_devices_with_tries()
print(len(devices))

# system.destroy_device()
devices = create_devices_with_tries()
print(len(devices))
