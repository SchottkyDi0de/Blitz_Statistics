from discord.ext.commands import CommandError


class BlackListException(CommandError):
    pass


class UserBanned(BlackListException):
    pass