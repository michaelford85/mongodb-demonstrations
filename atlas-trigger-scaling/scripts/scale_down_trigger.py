#!/usr/bin/env python3
"""Scale Atlas cluster down to the tier in SCALE_DOWN_TIER."""

from atlas_scaler import ConfigError, scale_cluster


def main() -> int:
    try:
        scale_cluster("SCALE_DOWN_TIER")
        return 0
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Scale-down failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
