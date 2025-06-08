class NotFoundError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

    def __repr__(self) -> str:
        return f"({self.__class__.__name__}message={self.message})"

    def __str__(self) -> str:
        return self.__repr__()
