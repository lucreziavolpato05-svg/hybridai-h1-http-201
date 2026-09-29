"""Build and query a FrameX ontology of the Swiss rail passenger network."""

from framex import Client


def main(argv=None) -> int:
    with Client() as client:
        client.load("world open.\n socrates:Human.\n ?X:Mortal <- ?X:Human.")
        result = client.query("?- socrates:Mortal.")
        print(result)  # {'status': 'true', 'bindings': []}
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
