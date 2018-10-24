
class Vec2D:
    __slots__ = ('x', 'y')

    def __init__(self, x, y=None):
        if y is None:
            x, y = x
        self.x = x
        self.y = y

    def __add__(self, o):
        x, y = o
        return type(self)(self.x + x, self.y + y)

    def __sub__(self, o):
        x, y = o
        return type(self)(self.x - x, self.y - y)

    def __mul__(self, o):
        if isinstance(o, (tuple, list, Vec2D)):
            x, y = o
        else:
            x = o
            y = o
        return Vec2D(self.x * x, self.y * y)

    def __getitem__(self, idx):
        if idx == 0:
            return self.x
        elif idx == 1:
            return self.y
        else:
            raise IndexError(f'Index {idx} out of range for {type(self)}')

    def __iter__(self):
        yield self.x
        yield self.y

    def __eq__(self, o):
        if not isinstance(o, Vec2D):
            return False
        ox, oy = o
        x, y = self
        return ox == x and oy == y

    def __bool__(self):
        return bool(self.x or self.y)

    def __hash__(self):
        return hash(tuple(self))

    def __repr__(self):
        return f"Vec2D({self.x}, {self.y})"

    def __str__(self):
        return self.__repr__()

