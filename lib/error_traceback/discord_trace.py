import discord
from discord.ext import commands


async def sent_err_info(ctx: commands.Context, client: discord.Client) -> None:
    await ctx.respond(
        f'`--------ERROR--------`'
        f'Command author: <@{ctx.author.id}>'
        f''
    )