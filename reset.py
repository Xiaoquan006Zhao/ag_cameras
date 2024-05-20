import time
from arena_api.system import system

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
				print(f'{sec_count + 1 } seconds passed ',
					'.' * sec_count, end='\r')
			tries += 1
		else:
			print(f'Created {len(devices)} device(s)')
			return devices
	else:
		raise Exception(f'No device found! Please connect a device and run '
						f'the example again.')


def example_entry_point():
	devices = create_devices_with_tries()

	for device in devices:
		print(f'Device used in the example:\n\t{device}')
		device.nodemap['UserSetSelector'].value = 'Default'
		device.nodemap['UserSetLoad'].execute()
		print('Device settings has been reset to \'Default\' user set')

	system.destroy_device()
	print('Destroyed all created devices')

if __name__ == '__main__':
	print('\nWARNING:\nTHIS EXAMPLE MIGHT CHANGE THE DEVICE(S) SETTINGS!')
	print('\nExample started\n')
	example_entry_point()
	print('\nExample finished successfully')
