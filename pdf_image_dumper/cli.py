from .runner import main as _runner_main


def main():
    """Entry point used by the console script. Calls package runner.main()."""
    _runner_main()


if __name__ == "__main__":
    main()
