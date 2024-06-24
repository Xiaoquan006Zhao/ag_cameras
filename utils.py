def preprocess_string(text):
    print(text)
    text = text.strip()
    text = text.lower()
    print(text)
    return text


def is_digit(app, button, string, original_text, original_color):
    preprocess_string(string)
    if not string.isdigit():
        app.show_popup(f"Invalid '{string}'' value. It must be an integer.")
        app.revert_button(button, original_text, original_color)
        return False

    return True
