import traceback

from discord.ext import commands
from discord import Bot
from lib.database.players import PlayersDB
from datetime import datetime

_admin_ids = [
    766019191836639273
]

class AdminCommand(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @commands.command()
    async def say_direct(self, ctx):
        try:
            data = ctx.message.content.split('/')
            if len(data) != 4:
                await ctx.author.send('```Uncorrect command format\n!say_direct/<!text: message>/<!guild: guild_id>/<!member: member_id or mention>```')
                return
            
            text, guild_id, target = data[1], data[2], data[3]
            if type(target) == str:
                guild = self.bot.get_guild(int(guild_id))
                user = guild.get_member(int(target))

            if user is None:
                await ctx.author.send('`Member not found or private`')
                return
            
            await user.send(text)
        
        except Exception:
            await ctx.author.send(f'```{traceback.format_exc()}```')

    @commands.command()
    async def say(self, ctx):
        try:
            data = ctx.message.content.split('/')
            if len(data) != 3:
                await ctx.author.send('```Uncorrect command format\n!say/<!text: message>/<!target: channel_id>```')
                return
            
            text, target = data[1], data[2]
            channel = self.bot.get_channel(int(target))
            await channel.send(text)
        except AttributeError:
            await ctx.author.send('`Channel not found or private`')
        except Exception:
            await ctx.author.send(f'```{traceback.format_exc()}```')
        else:
            ctx.author.senf('`Message sent successfully`')

    @commands.command()
    async def get_members(self, ctx):
        try:
            db = PlayersDB()
            for i, j in enumerate(db.db['members']):
                await ctx.author.send(f"```Player_id: {db.db['members'][j]['id']}\nPlayer_nickname: {db.db['members'][j]['nickname']}\nRegion: {db.db['members'][j]['region']}```")
            await ctx.author.send(f"`Count: {i+1}`")
        except Exception:
            await ctx.author.send(traceback.format_exc())

    @commands.command()
    async def get_servers(self, ctx):
        try:
            db = PlayersDB()
            for i in db['servers']:
                await ctx.author.send(f'```{i}```')
        except Exception:
            await ctx.author.send(f'```{traceback.format_exc()}```')

    @commands.command()
    async def get_sessions(self, ctx):
        if ctx.author.id in _admin_ids:
            try:
                db = PlayersDB().db
                full_time_format = '%Y.%m.%d [%H:%M:%S]'
                timestamp_format = '[%H:%M:%S]'
                for i, j in enumerate(db.db["members"]):
                    if db['members'][j]['last_stats'] == {}:
                        await ctx.author.send(f'```Member: {j} has no session stats```')
                    else:
                        timestamp = db['members'][j]['last_stats']['timestamp']
                        expiried_at = 43200 - (datetime.now().timestamp() - timestamp)

                        if expiried_at < 0:
                            expiried_at = datetime.utcfromtimestamp(-expiried_at).strftime(timestamp_format) + " Timestamp Expiried!"
                        else:
                            expiried_at = datetime.utcfromtimestamp(expiried_at).strftime(timestamp_format)

                        await ctx.author.send(f"\n\
```No: {i}\n\
Timestamp: {datetime.utcfromtimestamp(timestamp).strftime(full_time_format)}\n\
User_id: {j}\n\
User_game_nickname: {db['members'][j]['nickname']}\n\
Expiried at: {expiried_at}```")
            except Exception:
                await ctx.author.send(f'```{traceback.format_exc()}```')
            
def setup(bot):
    bot.add_cog(AdminCommand(bot))