import tkinter as tk
from tkinter import filedialog
from tkinter import font
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
import time
from utils import *

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

    save_directory_path = config.get("save_directory_path", "images/")
    os.makedirs(save_directory_path, exist_ok=True)
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
        start_time = time.time()
        self.root = root
        self.count = 0
        self.save_directory_path = save_directory_path
        self.Set_exposure = Set_exposure
        self.image_buffer = None
        self.camera_init()

        # Initialize custom naming pattern variables
        self.field = tk.StringVar()
        self.variety = tk.StringVar()
        self.population = tk.StringVar()
        self.treatment = tk.StringVar()
        self.exposure = tk.StringVar()
        self.image_count = tk.StringVar(value=str(self.count))
        self.comment = tk.StringVar()

        # Bind reset counter function to changes in input fields
        self.field.trace_add("write", self.reset_counter)
        self.variety.trace_add("write", self.reset_counter)
        self.population.trace_add("write", self.reset_counter)
        self.treatment.trace_add("write", self.reset_counter)

        # Main area for image
        self.main_frame = tk.Frame(root, height=300, width=500, bg="lightgreen")
        self.main_frame.grid(row=0, column=0, rowspan=7, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_propagate(False)

        # Initial image placeholder
        self.img_label = tk.Label(self.main_frame)
        self.img_label.pack(fill="both", expand=True)

        # Load and display the logo image
        self.logo_image = Image.open("logo.png")
        original_width, original_height = self.logo_image.size
        new_width = int(original_width * 0.15)
        new_height = int(original_height * 0.15)
        self.logo_image = self.logo_image.resize((new_width, new_height))
        self.logo_image = ImageTk.PhotoImage(self.logo_image)
        self.logo_label = tk.Label(root, image=self.logo_image)
        self.logo_label.grid(row=7, column=0, columnspan=2, padx=(30, 10), pady=0, sticky="w")

        # Buttons and inputs
        self.field_label = tk.Label(root, text="Field:", anchor="w")
        self.field_label.grid(row=0, column=1, padx=(0, 10), pady=0, sticky="ew")

        self.field_entry = tk.Entry(root, textvariable=self.field, width=18)
        self.field_entry.grid(row=0, column=2, padx=(0, 10), pady=0, sticky="ew")

        self.variety_label = tk.Label(root, text="Variety:", anchor="w")
        self.variety_label.grid(row=0, column=3, padx=(0, 10), pady=0, sticky="ew")

        self.variety_entry = tk.Entry(root, textvariable=self.variety, width=18)
        self.variety_entry.grid(row=0, column=4, padx=(0, 10), pady=0, sticky="ew")

        self.population_label = tk.Label(root, text="Population:", anchor="w")
        self.population_label.grid(row=1, column=1, padx=(0, 10), pady=0, sticky="ew")

        self.population_entry = tk.Entry(root, textvariable=self.population, width=18)
        self.population_entry.grid(row=1, column=2, padx=(0, 10), pady=0, sticky="ew")

        self.treatment_label = tk.Label(root, text="Treatment:", anchor="w")
        self.treatment_label.grid(row=1, column=3, padx=(0, 10), pady=0, sticky="ew")

        self.treatment_entry = tk.Entry(root, textvariable=self.treatment, width=18)
        self.treatment_entry.grid(row=1, column=4, padx=(0, 10), pady=0, sticky="ew")

        self.count_label = tk.Label(root, text="Image Counter:", anchor="w")
        self.count_label.grid(row=2, column=1, padx=(0, 10), pady=0, sticky="ew")

        self.count_entry = tk.Entry(root, textvariable=self.image_count, width=18)
        self.count_entry.grid(row=2, column=2, padx=(0, 10), pady=0, sticky="ew")

        self.exposure_label = tk.Label(root, text="Exposure:", anchor="w")
        self.exposure_label.grid(row=2, column=3, padx=(0, 10), pady=0, sticky="ew")

        self.exposure_entry = tk.Entry(root, textvariable=self.exposure, width=18)
        self.exposure_entry.grid(row=2, column=4, padx=(0, 10), pady=0, sticky="ew")

        self.comment_label = tk.Label(root, text="Comment:", anchor="w")
        self.comment_label.grid(row=3, column=1, padx=(0, 10), pady=0, sticky="ew")

        self.comment_entry = tk.Text(root, width=18, height=10)
        self.comment_entry.grid(row=3, column=2, columnspan=3, padx=(0, 10), pady=0, sticky="ew")

        self.button1 = tk.Button(root, text="Open Explorer", command=self.open_explorer, height=2, width=18)
        self.button1.grid(row=4, column=1, columnspan=2, padx=(0, 10), pady=0, sticky="ew")

        self.button2 = tk.Button(root, text="Save", command=self.save_image, height=2, width=18, bg="#90EE90")
        self.button2.grid(row=4, column=3, columnspan=2, padx=(0, 10), pady=0, sticky="ew")

        self.button3 = tk.Button(root, text="Start", command=self.start_process, height=2, width=18)
        self.button3.grid(row=5, column=1, columnspan=2, padx=(0, 10), pady=0, sticky="ew")

        self.button4 = tk.Button(
            root, text="Change Save Directory", command=self.select_save_directory, height=2, width=18
        )
        self.button4.grid(row=5, column=3, columnspan=2, padx=(0, 10), pady=0, sticky="ew")

        self.clear_comment_button = tk.Button(
            root, text="Clear Comment", command=self.clear_comment, height=2, width=18
        )
        self.clear_comment_button.grid(row=6, column=1, columnspan=2, padx=(0, 10), pady=0, sticky="ew")

        combined_images = np.zeros((2 * (h + 2 * border_size), 2 * (w + 2 * border_size), 3), dtype=np.uint8)
        view_image = cv2.resize(combined_images, (0, 0), fx=0.2, fy=0.2)
        self.update_image_grid(view_image)

        end_time = time.time()
        print(f"APP initialization took {end_time - start_time} seconds.")
        subprocess.Popen("osk", shell=True)

    def camera_init(self):
        # Initialize the cameras, their thread events, and main app thread condition
        start_time = time.time()
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

        end_time = time.time()
        print(f"All cameras initialization took {end_time - start_time} seconds.")

    # Function to handle button click event style and return the original text and color
    def button_click(self, button, display_text, bg_color="red"):
        original_text = button.cget("text")
        original_color = button.cget("bg")
        button.config(state="disabled", text=display_text, bg=bg_color)
        self.root.update_idletasks()

        return original_text, original_color

    def select_save_directory(self):
        global save_directory_path
        save_directory_path = filedialog.askdirectory(title="Select Save Directory", initialdir=os.getcwd())
        self.save_directory_path = save_directory_path

    # Function to revert button style to original text and color
    def revert_button(self, button, original_text, original_color):
        button.config(state="normal", text=original_text, bg=original_color)
        self.root.update_idletasks()

    def reset_counter(self, *args):
        self.count = 0
        self.image_count.set(str(self.count))

    def start_process(self):
        # Change button style to show that the process has started
        original_text, original_color = self.button_click(self.button3, display_text="Starting...")

        # For each frame, start the process in a separate thread
        for frame in self.frame_list:
            frame.startProcess()

        self.view_save_thread = threading.Thread(target=self.view_save_loop, args=())
        self.view_save_thread.daemon = True
        self.view_save_thread.start()

        self.button3 = tk.Button(root, text="Reload Config", command=self.reload_config, height=2, width=18)
        self.button3.grid(row=5, column=1, columnspan=2, padx=(0, 10), pady=0, sticky="ew")

    def reload_config(self):
        start_time = time.time()
        combined_images = np.zeros((2 * (h + 2 * border_size), 2 * (w + 2 * border_size), 3), dtype=np.uint8)
        view_image = cv2.resize(combined_images, (0, 0), fx=0.2, fy=0.2)
        self.update_image_grid(view_image)

        original_text, original_color = self.button_click(self.button3, display_text="Reloading Config...")
        safe_print("Reloading Config. Shutting down Cameras temporarily.")

        input_exposure = self.exposure.get().strip()
        if input_exposure != "":
            if not is_digit(app, self.button3, input_exposure, original_text, original_color):
                return

        on_closing(destory_root=False)

        # Arena api expects double type for exposure
        input_exposure = float(input_exposure)

        load_config()
        self.save_directory_path = save_directory_path
        if input_exposure != self.Set_exposure:
            self.Set_exposure = input_exposure
        else:
            self.Set_exposure = Set_exposure

        self.camera_init()

        for frame in self.frame_list:
            frame.startProcess()

        self.root.after(2000, lambda: self.revert_button(self.button3, original_text, original_color))

        end_time = time.time()
        print(f"Reloading config took {end_time - start_time} seconds.")

    def view_save_loop(self):
        while True:
            start_time = time.time()
            buffer_list = []
            for index, frame in enumerate(self.frame_list):
                img_array = frame.read()
                buffer_list.append(img_array)
            self.view_image(buffer_list)
            end_time = time.time()
            print(f"New Frame update took {end_time - start_time} seconds.")

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

        experiment = [
            self.field.get(),
            self.variety.get(),
            self.population.get(),
            self.treatment.get(),
            self.image_count.get(),
        ]

        # Check if the counter value is an integer
        for i, d in enumerate(experiment):
            if not is_digit(app, self.button2, d, original_text, original_color):
                return
            else:
                experiment[i] = int(d)

        subfolder_path = (
            f"field_{experiment[0]}_varity_{experiment[1]}_population_{experiment[2]}_treatment_{experiment[3]}/"
        )

        print(subfolder_path)
        # Create the subfolder if it does not exist
        subfolder_path = os.path.join(self.save_directory_path, subfolder_path)
        os.makedirs(subfolder_path, exist_ok=True)

        image_filename = f"image_{experiment[4]}.jpg"
        comment_filename = f"image_{experiment[4]}.txt"

        # Save the image and update the image count
        image_path = os.path.join(subfolder_path, image_filename)
        comment_path = os.path.join(subfolder_path, comment_filename)
        cv2.imwrite(image_path, self.image_buffer)
        print(f"Saved image {experiment[4]} as {image_path}")

        # Update the image count label and reset the image buffer
        self.image_count.set(str(experiment[4] + 1))
        self.image_buffer = None

        comment = self.comment_entry.get("1.0", tk.END).strip()
        if comment != "":
            with open(comment_path, "w") as f:
                f.write(comment)
            self.show_popup(f"Image and comment saved as {image_path}")

        else:
            self.show_popup(f"Image saved as {image_path}")

        # Revert the button style after 0.2seconds
        self.root.after(2000, lambda: self.revert_button(self.button2, original_text, original_color))

    def clear_comment(self):
        self.comment_entry.delete("1.0", tk.END)  # Deletes all text from the first character to the end

    # Show a popup message for a short duration
    def show_popup(self, message):
        popup = tk.Toplevel(self.root)
        popup.title("Notification")
        label = tk.Label(popup, text=message, padx=0, pady=10)

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
def on_closing(destory_root=True):
    start_time = time.time()

    print("Closing application...")
    print(f"Before closing cameras, total threads number: {threading.active_count()}")
    closing_threads = []
    for frame in app.frame_list:
        # Camera_off(frame)
        closing_threads.append(threading.Thread(target=Camera_off, args=(frame,), daemon=True))
        closing_threads[-1].start()

    for thread in closing_threads:
        thread.join()

    system.destroy_device()
    print(f"After closing cameras, total threads number: {threading.active_count()}")

    if destory_root:
        app.root.destroy()

    end_time = time.time()
    print(f"APP termination took {end_time - start_time} seconds.")


# Example usage
if __name__ == "__main__":
    print("Starting application...")
    root = tk.Tk()
    default_font = font.nametofont("TkDefaultFont")
    default_font.configure(size=12)
    app = ImageSaverApp(root, save_directory_path, Set_exposure)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
