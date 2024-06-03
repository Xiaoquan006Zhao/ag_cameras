import tkinter as tk
import cv2
import numpy as np
import threading
import time
import subprocess
import os
import json
import yaml
from sys import platform
from PIL import Image, ImageTk
from camera_setup import create_devices_with_tries, Camera_On, Camera_off
from arena_api.system import system

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


save_directory_path, Set_exposure, MAC_list, border_size = None, None, None, None


def load_config(config_file_path="config.yaml"):
    global save_directory_path, Set_exposure, MAC_list, border_size
    # Load configuration from YAML file
    with open(config_file_path, "r") as yaml_file:
        config = yaml.safe_load(yaml_file)

    save_directory_path = config["save_directory_path"]
    Set_exposure = config["Set_exposure"]
    MAC_list = config["MAC_list"]
    border_size = config.get("border_size", 10)  # Default value of 10


load_config("config.yaml")


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
                # camera_index = int(frame.which_camera)

                # device.nodemap.get_node("GevSCPD").value = 240000
                # offsetTime = camera_index * 80000
                # device.nodemap.get_node("GevSCFTD").value = offsetTime

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

    # Function to handle button click event style and return the original text and color
    def button_click(self, button, display_text, bg_color="red"):
        original_text = button.cget("text")
        original_color = button.cget("bg")
        button.config(state="disabled", text=display_text, bg=bg_color)
        self.root.update_idletasks()

        return original_text, original_color

    # Function to revert button style to original text and color
    def revert_button(self, button, original_text, original_color):
        button.config(state="normal", text=original_text, bg=original_color)
        self.root.update_idletasks()

    def start_process(self):
        # Change button style to show that the process has started
        original_text, original_color = self.button_click(self.button3, display_text="Starting...")

        # For each frame, start the process in a separate thread
        for frame in self.frame_list:
            frame.startProcess()

        self.view_save_thread = threading.Thread(target=self.view_save_loop, args=())
        self.view_save_thread.daemon = True
        self.view_save_thread.start()

        self.button3 = tk.Button(root, text="Reload Config", command=self.reload_config, height=2, width=20)
        self.button3.grid(row=6, column=1, padx=10, pady=10, sticky="ew")

    def reload_config(self):
        combined_images = np.zeros((2 * (h + 2 * border_size), 2 * (w + 2 * border_size), 3), dtype=np.uint8)
        view_image = cv2.resize(combined_images, (0, 0), fx=0.2, fy=0.2)
        self.update_image_grid(view_image)

        original_text, original_color = self.button_click(self.button3, display_text="Reloading Config...")
        safe_print("Reloading Config. Shutting down Cameras temporarily.")
        for frame in app.frame_list:
            Camera_off(frame)
        system.destroy_device()

        load_config()
        self.save_directory_path = save_directory_path
        self.Set_exposure = Set_exposure
        self.camera_init()

        for frame in self.frame_list:
            frame.startProcess()

        self.root.after(2000, lambda: self.revert_button(self.button3, original_text, original_color))

    def view_save_loop(self):
        while True:
            buffer_list = []
            for index, frame in enumerate(self.frame_list):
                img_array = frame.read()
                buffer_list.append(img_array)
            self.view_image(buffer_list)

    def update_image_grid(self, view_image):
        # Convert to PIL image and then to PhotoImage
        photo_img = Image.fromarray(cv2.cvtColor(view_image, cv2.COLOR_BGR2RGB))
        photo_img = ImageTk.PhotoImage(photo_img)
        self.img_label.config(image=photo_img)
        self.img_label.image = photo_img

    def view_image(self, image_array_list):
        buffer_bytes_per_pixel = 3
        # Create a 2x2 grid to display the images, including space for the borders
        combined_images = np.zeros(
            (2 * (h + 2 * border_size), 2 * (w + 2 * border_size), buffer_bytes_per_pixel), dtype=np.uint8
        )

        for _, image_array in enumerate(image_array_list):
            if image_array is not None:
                (npndarray, i) = image_array
                # Preprocess: lighting adjustment, undistortion, and cropping
                npndarray = cv2.convertScaleAbs(npndarray, alpha=10, beta=60)
                dst = cv2.remap(npndarray, mapx, mapy, cv2.INTER_LINEAR)
                dst = dst[y : y + h, x : x + w]
                cv2.imwrite(f"stitch/image_{i}_{self.count}.jpg", dst)

                # Add white border to the image
                dst_with_border = cv2.copyMakeBorder(
                    dst,
                    border_size,
                    border_size,
                    border_size,
                    border_size,
                    cv2.BORDER_CONSTANT,
                    value=[255, 255, 255],
                )

                # Put the image in the right place in the 2x2 grid
                row, col = divmod(i, 2)
                combined_images[
                    row * (h + 2 * border_size) : (row + 1) * (h + 2 * border_size),
                    col * (w + 2 * border_size) : (col + 1) * (w + 2 * border_size),
                    :,
                ] = dst_with_border

        # Resize the combined image and display it
        view_image = cv2.resize(combined_images, (0, 0), fx=0.2, fy=0.2)
        # Save the combined image to the image_buffer for future saving
        self.image_buffer = combined_images

        self.update_image_grid(view_image)

    def save_image(self):
        assert self.image_buffer is not None, "No image to save"
        original_text, original_color = self.button_click(self.button2, display_text="Saving...")

        # Get the naming prefix, subfolder name, and image count
        prefix = self.naming_prefix.get().strip()
        subfolder = self.subfolder_name.get().strip()
        count = self.image_count.get().strip()

        # Check if the counter value is an integer
        if not count.isdigit():
            self.show_popup("Invalid counter value. It must be an integer.")
            self.revert_button(self.button2, original_text, original_color)
            return

        self.count = int(count)

        # Create the subfolder if it does not exist
        subfolder_path = os.path.join(self.save_directory_path, subfolder)
        os.makedirs(subfolder_path, exist_ok=True)

        # Save the image with the appropriate naming pattern
        if prefix:
            filename = f"{prefix}_image{self.count}.jpg"
        else:
            filename = f"image_{self.count}.jpg"

        # Save the image and update the image count
        file_path = os.path.join(subfolder_path, filename)
        cv2.imwrite(file_path, self.image_buffer)
        print(f"Saved image {self.count} as {filename}")
        self.count += 1

        # Update the image count label and reset the image buffer
        self.image_count_label.config(text=f"Images Saved: {self.count - 1}")
        self.image_count.set(str(self.count))
        self.image_buffer = None
        self.show_popup(f"Image saved as {filename}")

        # Revert the button style after 0.2seconds
        self.root.after(2000, lambda: self.revert_button(self.button2, original_text, original_color))

    # Show a popup message for a short duration
    def show_popup(self, message):
        popup = tk.Toplevel(self.root)
        popup.title("Notification")
        label = tk.Label(popup, text=message, padx=10, pady=10)
        label.pack()
        popup.after(1000, popup.destroy)

    # Open the save directory in the file explorer
    def open_explorer(self):
        if platform == "win32":
            subprocess.run(["explorer", os.path.abspath(self.save_directory_path)])
        elif platform == "darwin":
            subprocess.run(["open", os.path.abspath(self.save_directory_path)])
        elif platform.startswith("linux"):
            subprocess.run(["xdg-open", os.path.abspath(self.save_directory_path)])


# Function to properly close the camera when the application is closed
def on_closing():
    print("Closing application...")
    print(f"Before closing cameras, total threads number: {threading.active_count()}")
    for frame in app.frame_list:
        Camera_off(frame)

    system.destroy_device()
    print(f"After closing cameras, total threads number: {threading.active_count()}")
    app.root.destroy()


# Example usage
if __name__ == "__main__":
    print("Starting application...")
    root = tk.Tk()
    app = ImageSaverApp(root, save_directory_path, Set_exposure)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
