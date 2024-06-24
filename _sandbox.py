def is_double(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


# Test cases
print(is_double("3.14"))  # True
print(is_double("42"))  # True (since integers can be represented as floats)
print(is_double("abc"))  # False
print(is_double("4.2e5"))  # True (scientific notation)
print(is_double(""))  # False
