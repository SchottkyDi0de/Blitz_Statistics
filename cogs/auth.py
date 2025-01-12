from discord.ui import Button, View
from discord import InteractionContextType, Option
from discord.ext import commands

from lib.data_classes.member_context import MixedApplicationContext
from lib.database.players import PlayersDB
from lib.embeds.info import InfoMSG
from lib.logger.logger import get_logger
from lib.error_handler.common import hook_exceptions
from lib.embeds.common import CommonMSG
from lib.settings.settings import Config
from lib.locale.locale import Text
from lib.utils.commands_wrapper import with_user_context_wrapper
from lib.utils.selectors import account_selector
from lib.utils.string_parser import insert_data
from lib.utils.slot_info import get_formatted_slot_info

_config = Config().get()
_log = get_logger(__file__, 'AuthCogLogger', 'logs/auth_cog_logs.log')


class Auth(commands.Cog):
    cog_command_error = hook_exceptions(_log)
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.common_msg = CommonMSG()
        self.db = PlayersDB()
    
    @commands.slash_command(
        contexts=[InteractionContextType.guild],
        description=Text().get('en').cmds.verify.descr.this,
        description_localizations={
            'ru': Text().get('ru').cmds.verify.descr.this,
            'pl': Text().get('pl').cmds.verify.descr.this,
            'uk': Text().get('ua').cmds.verify.descr.this
        }
    )
    @with_user_context_wrapper('verify')
    async def verify(
        self,
        mixed_ctx: MixedApplicationContext,
        account: Option(
            str,
            description=Text().get('en').frequent.common.slot,
            description_localizations={
                'ru': Text().get('ru').frequent.common.slot,
                'pl': Text().get('pl').frequent.common.slot,
                'uk': Text().get('ua').frequent.common.slot
            },
            autocomplete=account_selector,
            default=None
            )
        ):
        ctx = mixed_ctx.ctx
        m_ctx = mixed_ctx.m_ctx
                
        game_account, member, slot = m_ctx.game_account, m_ctx.member, m_ctx.slot
        
        if game_account.verified:
            await ctx.respond(
                embed=InfoMSG().custom(
                    Text().get(),
                    text=Text().get().cmds.verify.info.already_verified,
                    colour='green',
                    footer=get_formatted_slot_info(
                        slot=slot,
                        text=Text().get(),
                        game_account=game_account,
                        shorted=True,
                        clear_md=True
                    )
                ),
            )
            return
        
        await ctx.respond(
            embed=self.common_msg.verify(game_account=game_account, slot=slot),
            view=View(
                Button(
                    label=Text().get().cmds.verify.items.verify, 
                    url=insert_data(
                        _config.auth.wg_redirect_uri,
                        {
                            'region': game_account.region,
                            'requested_by': member.id,
                            'slot': slot.value
                        }
                    )
                )
            ),
            ephemeral=True
        )

def setup(bot: commands.Bot):
    bot.add_cog(Auth(bot))
