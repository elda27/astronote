import sub_module
from sub_mod import func

from astronote import notebook_entry


@notebook_entry
def main():
    print(sub_module.get_hello_world())
    print(func())


if __name__ == "__main__":
    main()
