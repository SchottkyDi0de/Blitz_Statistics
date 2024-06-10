from discord.ui import Button, View
from discord import ApplicationContext, Option
from discord.ext import commands

from lib.logger.logger import get_logger
from lib.error_handler.common import hook_exceptions
from lib.embeds.common import CommonMSG
from lib.settings.settings import Config, EnvConfig
from lib.locale.locale import Text
from lib.utils.string_parser import insert_data
from lib.utils.slot_info import get_formatted_slot_info
from lib.utils.standard_account_validate import standard_account_validate
from lib.data_classes.db_player import AccountSlotsEnum

_config = Config().get()
_env_config = EnvConfig()
_log = get_logger(__file__, 'AuthCogLogger', 'logs/auth_cog_logs.log')


class Auth(commands.Cog):
    cog_command_error = hook_exceptions(_log)
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.common_msg = CommonMSG()
    
    @commands.slash_command(
        description=Text().get('en').cmds.verify.descr.this,
        description_localizations={
            'ru': Text().get('ru').cmds.verify.descr.this,
            'pl': Text().get('pl').cmds.verify.descr.this,
            'uk': Text().get('ua').cmds.verify.descr.this
        }
    )
    async def verify(
        self, 
        ctx: ApplicationContext,
        region: Option(
            str,
            description=Text().get('en').frequent.common.region,
            description_localizations={
                'ru': Text().get('ru').frequent.common.region,
                'pl': Text().get('pl').frequent.common.region,
                'uk': Text().get('ua').frequent.common.region
            },
            required=True,
            choices=_config.default.available_regions
            ),
        account: Option(
            int,
            description=Text().get('en').frequent.common.slot,
            description_localizations={
                'ru': Text().get('ru').frequent.common.slot,
                'pl': Text().get('pl').frequent.common.slot,
                'uk': Text().get('ua').frequent.common.slot
            },
            choices=[x.value for x in AccountSlotsEnum],
            required=True,
            default=None
            )
        ):
        await Text().load_from_context(ctx)
        
        game_account, member, slot = await standard_account_validate(ctx.user.id, account)
        
        await ctx.respond(
            embed=self.common_msg.verify(),
            view=View(
                Button(
                    label=Text().get().cmds.verify.items.verify, 
                    url=insert_data(
                        _config.auth.wg_redirect_uri,
                        {
                            'region': region
                        }
                    )
                )
            ),
            ephemeral=True
        )

def setup(bot: commands.Bot):
    bot.add_cog(Auth(bot))