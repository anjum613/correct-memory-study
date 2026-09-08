"""Deterministic dependency installation ordering."""


def installation_order(graph: dict[str, tuple[str, ...]]) -> list[str]:
    order: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(package: str) -> None:
        if package in permanent:
            return
        if package in temporary:
            raise ValueError("dependency cycle")
        temporary.add(package)
        order.append(package)
        for dependency in graph.get(package, ()):
            visit(dependency)
        temporary.remove(package)
        permanent.add(package)

    for package in graph:
        visit(package)
    return order
