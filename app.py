import tkinter as tk
import cv2
import numpy as np
import threading
import time
import subprocess
import os
import json
from sys import platform
from PIL import Image, ImageTk
from camera_setup import create_devices_with_tries, Camera_On, height1, width1

# Load calibration data
mapx = mapy = None
with open("calibration_data.json", "r") as json_file:
    calibration_data = json.load(json_file)
mtx = np.array(calibration_data["camera_matrix"])
dist = np.array(calibration_data["distortion_coefficients"])
w = calibration_data["image_width"]
h = calibration_data["image_height"]
newcameramtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, newcameramtx, (w, h), 5)
x, y, w, h = roi

MAC_list = ["1C:0F:AF:0D:05:91", "1C:0F:AF:3D:3F:15", "1C:0F:AF:03:6B:4E", "1C:0F:AF:0E:B3:2D"]
# MAC_list = ["1C:0F:AF:3D:3F:15", "1C:0F:AF:03:6B:4E"]

def safe_print(*args, **kwargs):
    with threading.Lock():
        print(*args, **kwargs)

def int_to_mac(mac_value):
    try:
        mac_bytes = [
            (mac_value >> 40) & 0xFF,
            (mac_value >> 32) & 0xFF,
            (mac_value >> 24) & 0xFF,
            (mac_value >> 16) & 0xFF,
            (mac_value >> 8) & 0xFF,
            mac_value & 0xFF,
        ]
        mac_address = ":".join(f"{byte:02X}" for byte in mac_bytes)
        return mac_address
    except Exception as e:
        return f"Error converting MAC address: {e}"

class ImageSaverApp:
    def __init__(self, root, save_directory_path, Set_exposure):
        self.root = root
        self.count = 1
        self.save_directory_path = save_directory_path
        self.Set_exposure = Set_exposure
        self.image_buffer = None
        self.camera_init()

        # Initialize custom naming pattern variables
        self.naming_prefix = tk.StringVar()
        self.image_count = tk.StringVar(value=str(self.count))
        self.subfolder_name = tk.StringVar()

        # Main area for image
        self.main_frame = tk.Frame(root, height=300, width=500, bg='lightgreen')
        self.main_frame.grid(row=0, column=0, rowspan=6, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_propagate(False)

        # Initial image placeholder
        self.img_label = tk.Label(self.main_frame)
        self.img_label.pack(fill='both', expand=True)

        # Buttons and inputs
        self.prefix_label = tk.Label(root, text="Naming Prefix:")
        self.prefix_label.grid(row=0, column=1, padx=10, pady=10, sticky='ew')

        self.prefix_entry = tk.Entry(root, textvariable=self.naming_prefix, width=20)
        self.prefix_entry.grid(row=0, column=2, padx=10, pady=10, sticky='ew')

        self.count_label = tk.Label(root, text="Image Counter:")
        self.count_label.grid(row=1, column=1, padx=10, pady=10, sticky='ew')

        self.count_entry = tk.Entry(root, textvariable=self.image_count, width=20)
        self.count_entry.grid(row=1, column=2, padx=10, pady=10, sticky='ew')

        self.subfolder_label = tk.Label(root, text="Subfolder Name:")
        self.subfolder_label.grid(row=2, column=1, padx=10, pady=10, sticky='ew')

        self.subfolder_entry = tk.Entry(root, textvariable=self.subfolder_name, width=20)
        self.subfolder_entry.grid(row=2, column=2, padx=10, pady=10, sticky='ew')

        self.image_count_label = tk.Label(root, text=f"Images Saved: {self.count - 1}")
        self.image_count_label.grid(row=3, column=1, padx=10, pady=10, sticky='ew')

        self.button1 = tk.Button(root, text="Open Explorer", command=self.open_explorer, height=2, width=20)
        self.button1.grid(row=4, column=1, padx=10, pady=10, sticky='ew')

        self.button2 = tk.Button(root, text="Save", command=self.save_image, height=2, width=20)
        self.button2.grid(row=5, column=1, padx=10, pady=10, sticky='ew')

        self.button3 = tk.Button(root, text="Start", command=self.start_process, height=2, width=20)
        self.button3.grid(row=6, column=1, padx=10, pady=10, sticky='ew')

    def camera_init(self):
        self.frame_list = [None] * len(MAC_list)
        self.threading_event_list = [None] * len(MAC_list)
        self.threading_condition = threading.Condition()

        devices = create_devices_with_tries()

        for i in range(len(devices)):
            event = threading.Event()
            mac_address = int_to_mac(devices[i].nodemap.get_node("GevMACAddress").value)

            if mac_address in MAC_list:
                index = MAC_list.index(mac_address)
                self.threading_event_list[index] = event
                self.frame_list[index] = Camera_On(self.Set_exposure, index, devices[i], event, self.threading_condition)
            else:
                safe_print(f"MAC address {mac_address} not found in MAC_list")

        i = 0
        while True:
            masterFound = False
            restartSyncCheck = False

            for frame in self.frame_list:
                device = frame.device
                ptpStatus = device.nodemap.get_node('PtpStatus').value
                camera_index = int(frame.which_camera)

                device.nodemap.get_node('GevSCPD').value = 240000
                offsetTime = camera_index * 80000
                device.nodemap.get_node('GevSCFTD').value = offsetTime

                if ptpStatus == "Master":
                    if masterFound:
                        print("Two Masters. Wrong!")
                        restartSyncCheck = True
                        break
                    masterFound = True
                elif ptpStatus != "Slave":
                    restartSyncCheck = True
                    break

            if not restartSyncCheck and masterFound:
                break

            time.sleep(0.5)
            i += 1
            print(f"Trying {i}th Negotiate. MasterFound: {masterFound}.")

        for frame in self.frame_list:
            device = frame.device
            device.nodemap.get_node('AcquisitionStartMode').value = 'PTPSync'

    def start_process(self):
        original_text = self.button3.cget("text")
        original_color = self.button3.cget("bg")
        self.button3.config(state="disabled", text="Starting...", bg="red")
        self.root.update_idletasks()

        for frame in self.frame_list:
            frame.startProcess()

        def revert_button():
            self.button3.config(state="normal", text=original_text, bg=original_color)
            self.root.update_idletasks()

        self.root.after(2000, revert_button)
        threading.Thread(target=self.view_save_loop, daemon=True).start()

    def view_save_loop(self):
        while True:
            with threading.Lock():
                for threading_event in self.threading_event_list:
                    threading_event.wait()

                buffer_list = []

                for index, frame in enumerate(self.frame_list):
                    img_array = frame.read()
                    buffer_list.append(img_array)

                safe_print(f"All buffer Ready! {len(buffer_list)} frames received")
                self.view_image(buffer_list)

                for threading_event in self.threading_event_list:
                    threading_event.clear()

                with self.threading_condition:
                    self.threading_condition.notify_all()

    def view_image(self, image_array_list):
        buffer_bytes_per_pixel = 3
        self.button3.grid_remove()
        height = h
        width = w

        combined_images = np.zeros((2 * height, 2 * width, buffer_bytes_per_pixel), dtype=np.uint8)
        images = []

        for _, (npndarray, i) in enumerate(image_array_list):
            npndarray = cv2.convertScaleAbs(npndarray, alpha=10, beta=60)
            dst = cv2.remap(npndarray, mapx, mapy, cv2.INTER_LINEAR)
            dst = dst[y:y+h, x:x+w]
            images.insert(i, dst)

            row = i // 2
            col = i % 2
            combined_images[row * height:(row + 1) * height, col * width:(col + 1) * width, :] = dst

        view_image = cv2.resize(combined_images, (0, 0), fx=0.2, fy=0.2)
        photo_img = Image.fromarray(cv2.cvtColor(view_image, cv2.COLOR_BGR2RGB))
        photo_img = ImageTk.PhotoImage(photo_img)
        self.img_label.config(image=photo_img)
        self.img_label.image = photo_img

        self.image_buffer = combined_images

    def save_image(self):
        if self.image_buffer is not None:
            original_text = self.button2.cget("text")
            original_color = self.button2.cget("bg")
            self.button2.config(state="disabled", text="Saving...", bg="red")
            self.root.update_idletasks()

            prefix = self.naming_prefix.get().strip()
            subfolder = self.subfolder_name.get().strip()
            count = self.image_count.get().strip()

            if not count.isdigit():
                self.show_popup("Invalid counter value. It must be an integer.")
                self.button2.config(state="normal", text=original_text, bg=original_color)
                return

            self.count = int(count)

            subfolder_path = os.path.join(self.save_directory_path, subfolder)
            os.makedirs(subfolder_path, exist_ok=True)

            if prefix:
                filename = f"{prefix}_image{self.count}.jpg"
            else:
                filename = f"image_{self.count}_Exposure{int(self.Set_exposure)}.jpg"

            file_path = os.path.join(subfolder_path, filename)
            cv2.imwrite(file_path, self.image_buffer)
            print(f"Saved image {self.count} as {filename}")
            self.count += 1

            self.image_count_label.config(text=f"Images Saved: {self.count - 1}")
            self.image_count.set(str(self.count))
            self.image_buffer = None
            self.show_popup(f"Image saved as {filename}")

            def revert_button():
                self.button2.config(state="normal", text=original_text, bg=original_color)
                self.root.update_idletasks()

            self.root.after(1000, revert_button)

    def show_popup(self, message):
        popup = tk.Toplevel(self.root)
        popup.title("Notification")
        label = tk.Label(popup, text=message, padx=10, pady=10)
        label.pack()
        popup.after(1000, popup.destroy)

    def open_explorer(self):
        if platform == "win32":
            subprocess.run(['explorer', os.path.abspath(self.save_directory_path)])
        elif platform == "darwin":
            subprocess.run(['open', os.path.abspath(self.save_directory_path)])
        elif platform.startswith('linux'):
            subprocess.run(['xdg-open', os.path.abspath(self.save_directory_path)])

# Example usage
if __name__ == "__main__":
    print("Starting application...")
    root = tk.Tk()
    save_directory_path = "images/"
    Set_exposure = 2000.0
    app = ImageSaverApp(root, save_directory_path, Set_exposure)
    root.mainloop()
