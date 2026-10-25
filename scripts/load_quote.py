import argparse
import asyncio
import json
import math
import time

import httpx


def percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


async def run(args: argparse.Namespace) -> int:
    semaphore = asyncio.Semaphore(args.concurrency)
    results: list[tuple[float, int | None]] = []
    payload = {
        "cliente_id": args.cliente_id,
        "ramo": "VIDA_HIPOTECARIO",
        "consentimiento_version": args.consentimiento_version,
        "parametros": {
            "saldo_credito": args.saldo_credito,
            "ubicacion": {
                "municipio": args.municipio,
                "zona": args.zona,
                "estrato": args.estrato,
            },
        },
    }

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        async def request_one() -> None:
            async with semaphore:
                start = time.perf_counter()
                try:
                    response = await client.post(args.url, json=payload)
                    results.append(
                        (time.perf_counter() - start, response.status_code)
                    )
                except httpx.HTTPError:
                    results.append((time.perf_counter() - start, None))

        await asyncio.gather(*(request_one() for _ in range(args.requests)))

    latencies_ms = [duration * 1000 for duration, _ in results]
    failures = sum(status != 200 for _, status in results)
    p95 = percentile95(latencies_ms)
    print(
        json.dumps(
            {
                "requests": len(results),
                "failures": failures,
                "p95_ms": round(p95, 2),
                "target_p95_ms": args.target_p95_ms,
            },
            indent=2,
        )
    )
    return int(failures > 0 or p95 > args.target_p95_ms)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mide latencia extremo a extremo de cotización HU1.2.4."
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8001/api/v1/bff-web/cotizaciones",
    )
    parser.add_argument("--cliente-id", required=True)
    parser.add_argument("--consentimiento-version", default="1.0")
    parser.add_argument("--saldo-credito", type=int, default=200_000_000)
    parser.add_argument("--municipio", default="Bogotá D.C.")
    parser.add_argument("--zona", choices=("URBANA", "RURAL"), default="URBANA")
    parser.add_argument("--estrato", type=int, choices=range(1, 7), default=4)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--target-p95-ms", type=float, default=400.0)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1 or args.saldo_credito < 1:
        parser.error("requests, concurrency y saldo deben ser mayores que cero")
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
