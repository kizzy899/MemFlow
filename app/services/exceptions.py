class AppError(Exception):
    pass


class ConfigError(AppError):
    pass


class ParsingError(AppError):
    pass


class AIServiceError(AppError):
    pass


class NotionServiceError(AppError):
    pass


class TranslationError(AppError):
    pass


class XiaohongshuLoginError(AppError):
    pass

