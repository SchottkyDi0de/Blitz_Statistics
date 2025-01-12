import base64
from datetime import datetime
from io import BytesIO

from discord import Interaction, File

from lib.image.common import ImageGenCommon
from lib.data_classes.api.api_data import PlayerGlobalData, Player as PlayerFAPI, Achievements, TankStats, Statistics
from lib.data_classes.api.player_stats import All as AllPlayer
from lib.data_classes.api.tanks_stats import All as AllTank
from lib.data_classes.api.player_clan_stats import Clan
from lib.data_classes.replay_data_parsed import ParsedReplayData, PlayerResult, Player as PlayerFR, Rating
from lib.data_parser.parse_data import get_normalized_data
from lib.database.tankopedia import TankopediaDB
from lib.locale.locale import Text
from lib.logger.logger import get_logger
from lib.utils.string_parser import insert_data


_log = get_logger(__file__, 'SelectMenuLogger', 'logs/select_menu.log')


class SelectMenu:
    def _build_global_data(player: PlayerFR, playerres: PlayerResult, achievements: Achievements):
        return get_normalized_data(PlayerGlobalData(
            id=player.account_id,
            data=PlayerFAPI(
                achievements=achievements,
                tank_stats={'0': TankStats(all=AllTank(
                    spotted=0,
                    hits=0,
                    frags=8,
                    max_xp=0,
                    wins=0,
                    losses=0,
                    capture_points=0,
                    battles=0,
                    damage_dealt=0,
                    damage_received=0,
                    max_frags=0,
                    shoots=0,
                    frags8p=0,
                    xp=0,
                    win_and_survived=0,
                    survived_battles=0,
                    dropped_capture_points=0,
                    dropped_capture_points_agro=0,
                ), account_id=player.account_id, 
                tank_id=0, 
                max_xp=0, 
                max_frags=0, 
                in_garage_updated=0, 
                in_garage=0,
                frags=0,
                max_frags_tank_id=0,
                battle_life_time=0,
                last_battle_time=0,
                mark_of_mastery=0,
                )},
                statistics=Statistics(all=AllPlayer(
                    spotted=playerres.statistics.all.spotted,
                    hits=playerres.statistics.all.hits,
                    frags=playerres.statistics.all.frags,
                    max_xp=playerres.statistics.all.max_xp,
                    wins=playerres.statistics.all.wins,
                    losses=playerres.statistics.all.losses,
                    capture_points=playerres.statistics.all.capture_points,
                    battles=playerres.statistics.all.battles,
                    damage_dealt=playerres.statistics.all.damage_dealt,
                    damage_received=playerres.statistics.all.damage_received,
                    max_frags=playerres.statistics.all.max_frags,
                    shoots=playerres.statistics.all.shots,
                    frags8p=playerres.statistics.all.frags8p,
                    xp=playerres.statistics.all.xp,
                    win_and_survived=playerres.statistics.all.win_and_survived,
                    survived_battles=playerres.statistics.all.survived_battles,
                    dropped_capture_points=playerres.statistics.all.dropped_capture_points,
                    max_frags_tank_id=playerres.statistics.all.max_frags_tank_id,
                    shots=playerres.statistics.all.shots
                ),
                rating=Rating({}) if not playerres.statistics.rating else playerres.statistics.rating),
                clan_tag=player.info.clan_tag,
                clan_stats=Clan(members_count=0,
                                name="",
                                tag=player.info.clan_tag,
                                clan_id=0,
                                emblem_set_id=0,
                                created_at=0) if player.info.clan_tag else None
            ),
            region=player.info.region,
            lower_nickname=player.info.nickname.lower(),
            timestamp=datetime.now(),
            nickname=player.info.nickname
        ))

    def _get_normalized_ratio(ratio: float) -> int | float:
        ratio = round(ratio, 2)
        temp = str(ratio)
        if int(temp[temp.find('.') + 1:]):
            return ratio
        return int(temp[:-2])

    async def replay_select_callback(self, select, interaction: Interaction):
        await Text().load_from_context(self.ctx)
        self.data: ParsedReplayData
        _log.debug(f"buildng data for {select.values[0]}")

        nickname = select.values[0]
        need_cache = True

        for players in self.data.player_results:
                if players.player_info.nickname == nickname:
                    break

        if nickname in self.cache:
            _log.debug('get image from cache')
            need_cache = False
            bin_image = BytesIO(base64.b64decode(self.cache.get(nickname)))
        else:
            image_settings = self.db.get_image_settings(interaction.user.id)
            server_settings = self.sdb.get_server_settings(self.ctx)

            for player in self.data.players:
                if player.info.nickname == nickname:
                    break
            _log.debug(f"get achievements for {player.info.nickname}, generate image")

            achievements = await self.api.get_player_achievements(player.info.region, player.account_id)
            bin_image = ImageGenCommon().generate(self.ctx, SelectMenu._build_global_data(player, players, achievements), 
                                            image_settings, server_settings)
        
        if need_cache:
            self.cache.set(nickname, base64.b64encode(bin_image.read()))
            bin_image.seek(0)
        
        tank_dct = await TankopediaDB().get_tank_by_id(players.info.tank_id, region=player.info.region)
        tank_name = tank_dct['name'] if tank_dct else "Unknown"

        text = insert_data(Text().get().cmds.parse_replay.items.formenu, {
            'tank_name': tank_name,
            'nickname': nickname,
            'damage': players.info.damage_dealt,
            'spotted': players.info.damage_assisted_1,
            'xp': players.info.base_xp,
            'frags': players.info.n_enemies_destroyed,
            'blocked': players.info.damage_blocked,
            'shots': players.info.n_shots,
            "shots_hit": players.info.n_hits_dealt,
            'shots_penetrated': players.info.n_penetrations_dealt,
            'accuracy': str(SelectMenu._get_normalized_ratio(players.info.n_hits_dealt / players.info.n_shots * 100)) + '%',
            'penetration_ratio': str(SelectMenu._get_normalized_ratio(players.info.n_penetrations_dealt / players.info.n_hits_dealt * 100)) + '%',
        })

        await interaction.response.send_message(text, file=File(bin_image, 'stats.png'), ephemeral=True)