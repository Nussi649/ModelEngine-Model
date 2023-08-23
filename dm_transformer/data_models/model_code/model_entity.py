class ModelEntity:
    """
    CLASS ModelEntity
    Encapsulates all common functionality of classes that represent any model entity. The terminology implies the
    distinction between abstract Model Entities that can represent anything (such as Values, Units, Metadata) and
    concrete Model Objects that represent objects within the system being modeled.
    """
    def __init__(self, key, *, mini_mode=False):
        self._key = key
        self._mini_mode = mini_mode

    @classmethod
    def create_reduced(cls, key):
        instance = cls(key=key, mini_mode=True)
        return instance

    def upgrade(self):
        # abort if object is already in full mode
        if not self._mini_mode:
            return False
        self._mini_mode = False
        return True

    @property
    def key(self):
        return self._key

    @property
    def mini_mode(self):
        return self._mini_mode

    def __str__(self):
        return f'[{self.__class__.__name__}] {self.key}'
