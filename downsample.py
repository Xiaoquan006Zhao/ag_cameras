from PIL import Image


def lower_image_resolution(input_image_path, output_image_path, new_width, new_height):
    """
    Lowers the resolution of an image and saves it to the specified output path.

    :param input_image_path: Path to the input image file.
    :param output_image_path: Path where the resized image will be saved.
    :param new_width: The desired width of the resized image.
    :param new_height: The desired height of the resized image.
    """
    # Open the image file
    with Image.open(input_image_path) as img:
        # Resize the image
        resized_img = img.resize((new_width, new_height))
        # Save the resized image
        resized_img.save(output_image_path)
        print(f"Resized image saved to {output_image_path}")


if __name__ == "__main__":
    # Define the input and output paths
    id = 1

    input_path = f"image_{id}.jpg"
    output_path = f"image_{id}.jpg"

    # Define the new width and height
    new_width = 800  # Example width, change as needed
    new_height = 600  # Example height, change as needed

    # Call the function to resize the image
    lower_image_resolution(input_path, output_path, new_width, new_height)
