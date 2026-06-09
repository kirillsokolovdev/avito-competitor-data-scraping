# config.py
# Centralized application configuration loader.

import os
from dotenv import load_dotenv


# Load environment variables from the local .env file.
#
# Example:
#     BOT_TOKEN=123456:ABCDEF...
#
# After calling load_dotenv(), variables become available
# through os.environ and os.getenv().
#
# If the .env file does not exist, python-dotenv silently
# continues without raising an exception.
load_dotenv()


# Telegram Bot API token.
#
# os.getenv() returns:
# - the environment variable value if it exists
# - an empty string as fallback if the variable is missing
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")


# Fail fast if the token was not provided.
#
# This validation prevents the application from starting
# with an invalid configuration and producing less obvious
# runtime errors later.
if not BOT_TOKEN:
    raise ValueError("\n\nТокен бота не найден!\n")