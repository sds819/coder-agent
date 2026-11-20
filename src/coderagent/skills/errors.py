"""The errors of the skill hub: something did not work, and the reason is for a person."""


class SkillError(Exception):
    """A skill could not be fetched, checked or installed.

    The message is written for the user of the page, not for a log file.
    """


__all__ = ["SkillError"]
