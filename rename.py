import os


def rename_images(directory):
    for filename in os.listdir(directory):
        if filename.endswith(".jpg"):
            parts = filename.split("_")
            if len(parts) == 3 and parts[0] == "image":
                try:
                    side = int(parts[1])
                    index = int(parts[2].split(".")[0])

                    new_side = "l" if side == 0 else "r"
                    new_index = index + 30

                    new_filename = f"{new_index}_{new_side}.jpg"
                    old_filepath = os.path.join(directory, filename)
                    new_filepath = os.path.join(directory, new_filename)

                    os.rename(old_filepath, new_filepath)
                    print(f"Renamed {filename} to {new_filename}")
                except ValueError:
                    print(f"Skipping {filename}: unable to parse numbers")
            else:
                print(f"Skipping {filename}: does not match expected pattern")
        else:
            print(f"Skipping {filename}: not a .jpg file")


# Example usage
directory_path = "stitch/"
rename_images(directory_path)
