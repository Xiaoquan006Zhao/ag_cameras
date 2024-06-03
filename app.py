import tkinter as tk
import cv2
import numpy as np
import threading
import time
import subprocess
import os
import yaml
from sys import platform
from PIL import Image, ImageTk
from camera_setup import create_devices_with_tries, Camera_On, Camera_off
from arena_api.system import system

# Load configuration from YAML file
with open("config.yaml", "r") as yaml_file:
    config = yaml.safe_load(yaml_file)

save_directory_path = config["save_directory_path"]
Set_exposure = config["Set_exposure"]
MAC_list = config["MAC_list"]
border_size = config.get("border_size", 10)  # Set a default value if not provided

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


# Function to thread safe print to the console
def safe_print(*args, **kwargs):
    with threading.Lock():
        print(*args, **kwargs)


# Function to convert an integer to a MAC address string
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
        self.main_frame = tk.Frame(root, height=300, width=500, bg="lightgreen")
        self.main_frame.grid(row=0, column=0, rowspan=6, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_propagate(False)

        # Initial image placeholder
        self.img_label = tk.Label(self.main_frame)
        self.img_label.pack(fill="both", expand=True)

        # Buttons and inputs
        self.subfolder_label = tk.Label(root, text="Subfolder Name:")
        self.subfolder_label.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.subfolder_entry = tk.Entry(root, textvariable=self.subfolder_name, width=20)
        self.subfolder_entry.grid(row=0, column=2, padx=10, pady=10, sticky="ew")

        self.prefix_label = tk.Label(root, text="Naming Prefix:")
        self.prefix_label.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        self.prefix_entry = tk.Entry(root, textvariable=self.naming_prefix, width=20)
        self.prefix_entry.grid(row=1, column=2, padx=10, pady=10, sticky="ew")

        self.count_label = tk.Label(root, text="Image Counter:")
        self.count_label.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        self.count_entry = tk.Entry(root, textvariable=self.image_count, width=20)
        self.count_entry.grid(row=2, column=2, padx=10, pady=10, sticky="ew")

        self.image_count_label = tk.Label(root, text=f"Images Saved: {self.count - 1}")
        self.image_count_label.grid(row=3, column=1, padx=10, pady=10, sticky="ew")

        self.button1 = tk.Button(root, text="Open Explorer", command=self.open_explorer, height=2, width=20)
        self.button1.grid(row=4, column=1, padx=10, pady=10, sticky="ew")

        self.button2 = tk.Button(root, text="Save", command=self.save_image, height=2, width=20)
        self.button2.grid(row=5, column=1, padx=10, pady=10, sticky="ew")

        self.button3 = tk.Button(root, text="Start", command=self.start_process, height=2, width=20)
        self.button3.grid(row=6, column=1, padx=10, pady=10, sticky="ew")

    def camera_init(self):
        # Initialize the cameras, their thread events, and main app thread condition
        self.frame_list = [None] * len(MAC_list)
        devices = create_devices_with_tries()

        # Initialize the cameras in MAC_list order
        for i in range(len(devices)):
            mac_address = int_to_mac(devices[i].nodemap.get_node("GevMACAddress").value)
            assert mac_address in MAC_list, f"MAC address {mac_address} not found in MAC_list"
            index = MAC_list.index(mac_address)

            # Populate frame_list and threading_event_list
            self.frame_list[index] = Camera_On(self.Set_exposure, index, devices[i])

        # Wait for all cameras to negotiate PTP Sync
        i = 0
        while True:
            masterFound = False
            restartSyncCheck = False

            for frame in self.frame_list:
                device = frame.device
                ptpStatus = device.nodemap.get_node("PtpStatus").value

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

            time.sleep(1)
            i += 1
            print(f"Trying {i}th Negotiate. MasterFound: {masterFound}.")

        for frame in self.frame_list:
            print(f"Creating camera_{frame.which_camera} (Status: {frame.device.nodemap.get_node('PtpStatus').value})")

    def button_click(self, button, display_text, bg_color="red"):
        original_text = self.button3.cget("text")
        original_color = self.button3.cget("bg")
        button.config(state="disabled", text=display_text, bg=bg_color)
        self.root.update_idletasks()

        return original_text, original_color

    def revert_button(self, button, original_text, original_color):
        button.config(state="normal", text=original_text, bg=original_color)
        self.root.update_idletasks()

    def start_process(self):
        original_text, original_color = self.button_click(self.button3, display_text="Starting...")

        for frame in self.frame_list:
            frame.startProcess()

        self.root.after(2000, lambda: self.revert_button(self.button3, original_text, original_color))
        threading.Thread(target=self.view_save_loop, daemon=True).start()

    def view_save_loop(self):
        while True:
            buffer_list = []
            for index, frame in enumerate(self.frame_list):
                img_array = frame.read()
                buffer_list.append(img_array)

            self.view_image(buffer_list)

    def view_image(self, image_array_list):
        buffer_bytes_per_pixel = 3

        self.button3.grid_remove()
        height = h
        width = w

        combined_images = np.zeros(
            (2 * (height + 2 * border_size), 2 * (width + 2 * border_size), buffer_bytes_per_pixel), np.uint8
        )

        for idx, image_array in enumerate(image_array_list):
            row_idx = idx // 2
            col_idx = idx % 2
            resized_image_array = cv2.remap(image_array, mapx, mapy, cv2.INTER_LINEAR)
            resized_image_array = cv2.cvtColor(resized_image_array, cv2.COLOR_BGR2RGB)
            combined_images[
                row_idx * (height + 2 * border_size) : (row_idx + 1) * (height + 2 * border_size),
                col_idx * (width + 2 * border_size) : (col_idx + 1) * (width + 2 * border_size),
            ] = cv2.copyMakeBorder(
                resized_image_array,
                border_size,
                border_size,
                border_size,
                border_size,
                cv2.BORDER_CONSTANT,
                None,
                (0, 0, 0),
            )

        self.image_buffer = combined_images

        combined_images_pil = Image.fromarray(combined_images)
        imgtk = ImageTk.PhotoImage(image=combined_images_pil)
        self.img_label.configure(image=imgtk)
        self.img_label.image = imgtk

    def open_explorer(self):
        path = os.path.realpath(self.save_directory_path)
        if platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path])
        elif platform.startswith("win32"):
            os.startfile(path)
        elif platform.startswith("darwin"):
            subprocess.Popen(["open", path])

    def save_image(self):
        original_text, original_color = self.button_click(self.button2, display_text="Saving...", bg_color="red")

        if self.image_buffer is None:
            print("No image to save!")
            return

        folder_name = self.subfolder_name.get()
        save_dir = os.path.join(self.save_directory_path, folder_name)

        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        prefix = self.naming_prefix.get()
        count_str = self.image_count.get()
        file_name = f"{prefix}_{count_str}.png"
        file_path = os.path.join(save_dir, file_name)
        image_to_save = cv2.cvtColor(self.image_buffer, cv2.COLOR_RGB2BGR)

        cv2.imwrite(file_path, image_to_save)
        print(f"Image saved at: {file_path}")

        self.count += 1
        self.image_count.set(str(self.count))
        self.image_count_label.config(text=f"Images Saved: {self.count - 1}")
        self.revert_button(self.button2, original_text, original_color)


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1200x800")
    root.title("Image Saver App")
    app = ImageSaverApp(root, save_directory_path, Set_exposure)
    root.mainloop()
