# utils/exceptions.py

class AuthenticationError(Exception):
    """Base class for all authentication-related failures"""
    def __init__(self, message: str, fatal: bool = False):
        self.message = message
        self.fatal = fatal  # True if no retry possible (e.g., wrong password)
        super().__init__(self.message)


class InvalidCredentialsError(AuthenticationError):
    """Wrong username/password or wrong broker URL"""
    def __init__(self):
        super().__init__(
            "Invalid username, password, or broker TMS URL. Cannot continue.",
            fatal=True
        )


class MaxCaptchaRetriesExceeded(AuthenticationError):
    """All login attempts failed due to persistent CAPTCHA issues"""
    def __init__(self, max_attempts: int):
        super().__init__(
            f"Login failed after {max_attempts} attempts. Persistent CAPTCHA solving issues.",
            fatal=False  # Could be temporary (e.g., low balance, bad image)
        )