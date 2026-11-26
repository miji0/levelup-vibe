class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, *, fields=None, retry_after=None):
        self.status, self.code, self.message = status, code, message
        self.fields, self.retry_after = fields, retry_after
