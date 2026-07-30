import json
import os
import pathlib
import subprocess
import tempfile
import uuid


STATE_SCHEMA = 1
STATE_KEYS = (
    "firmwareType",
    "partitionChoices",
    "locale",
    "region",
    "zone",
    "keyboardLayout",
    "keyboardVariant",
    "keyboardVConsoleKeymap",
    "username",
    "fullname",
    "hostname",
)
SECRET_KEYS = ("password", "rootPassword", "luksPassphrase")


class TransactionFailure(RuntimeError):
    pass


def collect_state(value, transaction_id):
    state = {"schema": STATE_SCHEMA, "transaction_id": transaction_id}
    for key in STATE_KEYS:
        item = value(key)
        if item is not None:
            state[key] = item
    for key in SECRET_KEYS:
        if key in state:
            raise TransactionFailure(f"secret key crossed installer boundary: {key}")
    return state


def atomic_json(path, value, mode=0o600):
    path = pathlib.Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def new_transaction_id():
    return uuid.uuid4().hex


def paths(runtime_directory, transaction_id):
    base = pathlib.Path(runtime_directory) / transaction_id
    return {
        "base": base,
        "state": base / "state.json",
        "plan": base / "plan.json",
        "journal": base / "journal.json",
    }


def execute(arguments):
    if not isinstance(arguments, (list, tuple)) or not arguments:
        raise TransactionFailure("command must be a non-empty argument array")
    if not all(isinstance(argument, str) and "\0" not in argument for argument in arguments):
        raise TransactionFailure("command arguments must be NUL-free strings")
    try:
        subprocess.run(arguments, check=True, shell=False)
    except (OSError, subprocess.CalledProcessError) as error:
        raise TransactionFailure(str(error)) from error
