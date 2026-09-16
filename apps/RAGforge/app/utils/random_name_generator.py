import uuid


def random_name_generator(file_extension: str) -> str:
    """
    Generate a random name for a file.
    with format: <random_string>.<file_extension>
    where <uid> is a random UUID and <extension> is the file extension.
    """
    random_string = uuid.uuid4().hex
    if not file_extension.startswith("."):
        file_extension = "." + file_extension
    return f"{random_string}{file_extension}"
