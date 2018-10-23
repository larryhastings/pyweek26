
class Vec2DIterator:
    def __init__(self, v):
        self.v = v
        self.i = 0

    def __next__(self):
        if self.i == 0:
            self.i = 1
            return self.v.x
        if self.i == 1:
            self.i = 2
            return self.v.y
        raise StopIteration

class Vec2D:
    def __init__(self, x, y=None):
        if y is None:
            x, y = x
        self.x = x
        self.y = y

    def __add__(self, o):
        x, y = o
        return Vec2D(self.x + x, self.y + y)

    def __sub__(self, o):
        x, y = o
        return Vec2D(self.x - x, self.y - y)

    def __mul__(self, o):
        if isinstance(o, (tuple, list, Vec2D)):
            x, y = o
        else:
            x = o
            y = o
        return Vec2D(self.x * x, self.y * y)

    def __iter__(self):
        return Vec2DIterator(self)

    def __bool__(self):
        return bool(self.x or self.y)

    def __hash__(self):
        return (self.y * 1024) + self.x

    def __repr__(self):
        return f"Vec2D({self.x}, {self.y})"

    def __eq__(self, o):
        return isinstance(o, Vec2D) and (o.x == self.x) and (o.y == self.y)

    def __str__(self):
        return self.__repr__()
