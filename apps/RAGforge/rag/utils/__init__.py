import tiktoken

encoder = tiktoken.get_encoding("cl100k_base")


def num_tokens_from_string(string: str) -> int:
    """
    Calculate the number of tokens in a string using the tiktoken library.

    Args:
        string (str): The input string.

    Returns:
        int: The number of tokens in the string.
    """
    try:
        return len(encoder.encode(string))
    except Exception:
        return 0
