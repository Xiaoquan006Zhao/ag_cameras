import subprocess
import time

# Open the on-screen keyboard (osk.exe)
osk_process = subprocess.Popen("osk", shell=True)
# Wait for 1 seconds
time.sleep(1)

# Call the batch file to close the on-screen keyboard
subprocess.Popen("close_osk.bat", shell=True)
