def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_file(path, data: bytes):
    with open(path, "wb") as f:
        f.write(data)