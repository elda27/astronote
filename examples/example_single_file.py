from astronote import notebook_entry


def func() -> str:
    return "This is a sub-function, not a notebook entry."


@notebook_entry
def main() -> str:
    return func()


if __name__ == "__main__":
    main()
