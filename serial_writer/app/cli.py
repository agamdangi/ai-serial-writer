"""Backward-compatible import for the inbound CLI adapter."""

from serial_writer.interfaces.cli import app, get_run_dir

__all__ = ["app", "get_run_dir"]


if __name__ == "__main__":
    app()
