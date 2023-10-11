import json
import asyncio
from time import time
from datetime import datetime

from cacheout import FIFOCache

import aiohttp

from lib.data_classes.api_data import PlayerGlobalData
from lib.data_classes.palyer_clan_stats import ClanStats
from lib.data_classes.player_achievements import Achievements
from lib.data_classes.player_stats import PlayerStats
from lib.data_classes.tanks_stats import TankStats
from lib.data_parser.parse_data import get_normalized_data
from lib.database.players import PlayersDB
from lib.exceptions import api as api_exceptions
from lib.logger.logger import get_logger
from lib.settings import settings

_log = get_logger(__name__, 'AsyncWotbAPILogger', 'logs/async_wotb_api.log')
st = settings.SttObject()

class API:
    def __init__(self) -> None:
        self.cache = FIFOCache(maxsize=100, ttl=60)
        self.player = PlayerGlobalData()
        self.exact = True
        self.raw_dict = False

        self.start_time = 0

    def _get_id_by_reg(self, reg: str):
        reg = reg.lower()
        if reg == 'ru':
            return st.LT_APP_ID
        elif reg in ['eu', 'com', 'asia', 'na', 'as']:
            return st.WG_APP_ID
        raise api_exceptions.UncorrectRegion(f'Uncorrect region: {reg}')

    def _reg_normalizer(self, reg: str) -> str:
        if reg in ['ru', 'eu', 'asia']:
            return reg
        if reg == 'na':
            return 'com'
        else:
            raise api_exceptions.UncorrectRegion(f'Uncorrect region: {reg}')
        
    async def response_handler(self, response: aiohttp.ClientResponse, check_data_status: bool = True) -> dict:
        """
        Asynchronously handles the response from the API and returns the data as a dictionary.

        Args:
            response (aiohttp.ClientResponse): The response object received from the API.
            check_data_status (bool, optional): Flag to indicate whether to check the status of the data. Defaults to True.

        Raises:
            api_exceptions.APIError: Raised if the response status is not 200 or the data status is not 'ok'.

        Returns:
            dict: The data returned from the API as a dictionary.
        """
        if response.status != 200:
            raise api_exceptions.APIError()
        
        data = await response.text()
        data = json.loads(data)

        if check_data_status:
            if data['status'] != 'ok':
                raise api_exceptions.APIError()
        
        return data

    def _get_url_by_reg(self, reg: str):
        reg = self._reg_normalizer(reg)
        match reg:
            case 'ru':
                return 'papi.tanksblitz.ru'
            case 'eu':
                return 'api.wotblitz.eu'
            case 'asia':
                return 'api.wotblitz.asia'
            case 'com':
                return 'api.wotblitz.com'
            case _:
                raise api_exceptions.UncorrectRegion(f'Uncorrect region: {reg}')

    async def get_tankopedia(self, region: str = 'ru') -> dict:

        _log.debug('Get tankopedia data')
        url_get_tankopedia = (
            f'https://{self._get_url_by_reg(region)}/wotb/encyclopedia/vehicles/'
            f'?application_id={self._get_id_by_reg(region)}&fields='
            f'-description%2C+-engines%2C+-guns%2C-next_tanks%2C+-prices_xp%2C+'
            f'-suspensions%2C+-turrets%2C+-cost%2C+-default_profile%2C+-modules_tree%2C+-images'
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url_get_tankopedia, verify_ssl=False) as response:
                data = await self.response_handler(response, False)

                if data['status'] == 'error':
                    _log.error(f'Error get tankopedia, bad response status: \n{data}')
                    raise api_exceptions.APIError(f'Bad API response status {data}')

                return data
            
    def done_callback(self, task: asyncio.Task):
        _log.debug(f'{task.get_name()} done\n')

    async def get_stats(self, search: str, region: str, exact: bool = True, raw_dict: bool = False) -> PlayerGlobalData:
        if search is None or region is None:
            self.exact = True
            self.raw_dict = False
            raise api_exceptions.APIError('Empty parameter search or region')
        
        self.cache.delete_expired()

        self.exact = exact
        self.raw_dict = raw_dict

        _log.debug('Get stats method called, arguments: %s, %s', search, region)
        self.start_time = time()
        need_cached = False

        cached_data = self.cache.get((search.lower(), region))

        if cached_data is None:
            need_cached = True
            _log.debug('Cache miss')
        else:
            _log.debug('Returned cached player data')
            return PlayerGlobalData(cached_data)

        account_id = await self.get_account_id(region=region, nickname=search)

        tasks = [
            self.get_player_stats,
            self.get_player_tanks_stats,
            self.get_player_clan_stats,
            self.get_player_achievements
        ]
        task_names = [
            'get_player_stats',
            'get_player_tanks_stats',
            'get_player_clan_stats',
            'get_player_achievements'
        ]

        async with aiohttp.ClientSession() as self.session:
            async with asyncio.TaskGroup() as tg:
                for i, task in enumerate(tasks):
                    task = tg.create_task(task(account_id=account_id, region=region, nickname=search))
                    task.set_name(task_names[i])
                    task.add_done_callback(self.done_callback)
            
        self.player.timestamp = datetime.now().timestamp()

        if need_cached:
            self.cache.set((search.lower(), region), self.player.to_dict())
            _log.debug('Data add to cache')

        if self.raw_dict:
            return self.player.to_dict()

        _log.debug(f'All requests time: {time() - self.start_time}')
        return get_normalized_data(self.player)

    async def get_account_id(self, region: str, nickname: str, **kwargs) -> None:
        url_get_id = (
            f'https://{self._get_url_by_reg(region)}/wotb/account/list/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&search={nickname}'
            f'&type={"exact" if self.exact else "startswith"}'
        )

        async with aiohttp.ClientSession() as self.session:
            async with self.session.get(url_get_id, verify_ssl=False) as response:
                data = await self.response_handler(response, False)

                if data['status'] == 'error':
                    match data['error']['code']:
                        case 407 | 402:
                            raise api_exceptions.UncorrectName()
                        
                if data['meta']['count'] > 1:
                    raise api_exceptions.MoreThanOnePlayerFound()
                elif data['meta']['count'] == 0:
                    raise api_exceptions.NoPlayersFound()

                account_id: int = data['data'][0]['account_id']
                return account_id

    async def get_player_stats(self, region: str, account_id: str, **kwargs) -> PlayerStats:
        _log.debug('Get main stats started')
        url_get_stats = (
            f'https://{self._get_url_by_reg(region)}/wotb/account/info/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&account_id={account_id}'
            f'&extra=statistics.rating'
            f'&fields=-statistics.clan'
        )

        async with self.session.get(url_get_stats, verify_ssl=False) as response:
            data = await self.response_handler(response)

        try:
            battles = data['data'][str(account_id)]['statistics']['all']['battles']
        except KeyError:
            raise api_exceptions.EmptyDataError('Cannot acces to field "battles" in the output data')
        else:
            if battles < 100:
                raise api_exceptions.NeedMoreBattlesError('Need more battles for generate statistics')

        data['data'] = data['data'][str(account_id)]
        data = PlayerStats(data)

        self.player.id = account_id
        self.player.data.statistics = data.data.statistics
        self.player.nickname = data.data.nickname

    async def get_player_achievements(self, region: str, account_id: str, **kwargs) -> None:
        _log.debug('Get achievements started')
        url_get_achievements = (
            f'https://{self._get_url_by_reg(region)}/wotb/account/achievements/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&fields=-max_series&account_id={account_id}'
        )

        async with self.session.get(url_get_achievements, verify_ssl=False) as response:
            data = await self.response_handler(response)

        self.player.data.achievements = Achievements(data['data'][str(account_id)]['achievements'])

    async def get_player_clan_stats(self, region: str, account_id: str | int, **kwargs):
        _log.debug('Get clan stats started')
        url_get_clan_stats = (
            f'https://{self._get_url_by_reg(region)}/wotb/clans/accountinfo/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&account_id={account_id}'
            f'&extra=clan'
        )

        async with self.session.get(url_get_clan_stats, verify_ssl=False) as response:
            data = await self.response_handler(response)

        if data['data'][str(account_id)] is None:
            self.player.data.clan_tag = None
            self.player.data.clan_stats = None
            return
        
        data['data'] = data['data'][str(account_id)]
        data = ClanStats(data)
        self.player.data.clan_tag = data.data.clan.tag
        self.player.data.clan_stats = data.data.clan

    async def get_player_tanks_stats(self, region: str, account_id: str, nickname: str,  **kwargs):
        _log.debug('Get player tank stats started')
        url_get_tanks_stats = (
            f'https://{self._get_url_by_reg(region)}/wotb/tanks/stats/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&account_id={account_id}'
        )
        async with self.session.get(url_get_tanks_stats, verify_ssl=False) as response:
            data = await self.response_handler(response)

        tanks_stats: list[TankStats] = []

        for i in data['data'][str(account_id)]:
            tanks_stats.append(TankStats(i))

        self.player.region = self._reg_normalizer(region)
        self.player.lower_nickname = nickname.lower()
        self.player.data.tank_stats = tanks_stats


def test(nickname='cnJIuHTeP_KPbIca', region='ru', save_to_database: bool = False):
    db = PlayersDB()
    api = API()
    data = asyncio.run(api.get_stats(nickname, region), debug=True)
    
    if save_to_database:
        db.set_member_last_stats(766019191836639273, data.to_dict())

    return data
