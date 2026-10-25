from pathlib import Path
import sys

from grpc_tools import protoc


ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "contracts" / "proto"
PROTO_FILE = PROTO_DIR / "perfilamiento.proto"
SERVICES = ("identity_service", "motor_cotizacion")


def main() -> None:
    for service in SERVICES:
        output = ROOT / service / "src" / "infrastructure" / "grpc"
        result = protoc.main(
            [
                "grpc_tools.protoc",
                f"-I{PROTO_DIR}",
                f"--python_out={output}",
                f"--grpc_python_out={output}",
                str(PROTO_FILE),
            ]
        )
        if result:
            raise SystemExit(result)

        grpc_file = output / "perfilamiento_pb2_grpc.py"
        source = grpc_file.read_text(encoding="utf-8")
        source = source.replace(
            "import perfilamiento_pb2 as perfilamiento__pb2",
            "from . import perfilamiento_pb2 as perfilamiento__pb2",
        )
        grpc_file.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
