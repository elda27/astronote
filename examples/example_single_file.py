from astronote import notebook_entry


def func() -> str:
    return "This is a sub-function, not a notebook entry."


def calc(x: int, y: int) -> int:
    return x + y


@notebook_entry
def main(a: int = 10, b: int = 20) -> str:
    result = calc(a, b)
    return f"The result of calc({a}, {b}) is {result}"


if __name__ == "__main__":
    main()
