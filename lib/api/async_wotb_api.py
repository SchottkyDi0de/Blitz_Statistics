from pprint import pprint
import json
import asyncio
import traceback
from time import time
from datetime import datetime
from typing import Dict, Union

import aiohttp
from aiohttp import client_exceptions
from the_retry import retry
from asynciolimiter import Limiter
from cacheout import FIFOCache

from lib.utils.string_parser import insert_data
from lib.data_classes.api_data import PlayerGlobalData
from lib.data_classes.palyer_clan_stats import ClanStats
from lib.data_classes.player_achievements import Achievements
from lib.data_classes.player_stats import PlayerStats, PlayerData
from lib.data_classes.tanks_stats import TankStats
from lib.utils.singleton_factory import singleton
from lib.data_parser.parse_data import get_normalized_data
from lib.exceptions import api as api_exceptions
from lib.logger.logger import get_logger
from lib.settings.settings import Config, EnvConfig
from lib.data_classes.db_player import DBPlayer, ImageSettings

_log = get_logger(__name__, 'AsyncWotbAPILogger', 'logs/async_wotb_api.log')
_config = Config().get()


@singleton
class API:
    def __init__(self) -> None:
        self.exact = True
        self.raw_dict = False
        self._palyers_stats = []
        self.start_time = 0
        self.rate_limiter = Limiter(19)
        self.cache = FIFOCache(maxsize=100, ttl=60)

        self.player_stats = {}
        self.player = {}

    def _get_id_by_reg(self, reg: str) -> str:
        reg = reg.lower()
        if reg == 'ru':
            return next(EnvConfig.LT_APP_IDS)
        elif reg in ['eu', 'com', 'asia', 'na', 'as']:
            tok = next(EnvConfig.WG_APP_IDS)
            _log.debug(f'Used app ID: {tok}')
            return tok
        raise api_exceptions.UncorrectRegion(f'Uncorrect region: {reg}')

    def _reg_normalizer(self, reg: str) -> str:
        if reg in ['ru', 'eu', 'asia']:
            return reg
        if reg == 'na':
            return 'com'
        else:
            raise api_exceptions.UncorrectRegion(f'Uncorrect region: {reg}')
        
    async def response_handler(
            self,
            response: aiohttp.ClientResponse, 
            check_data_status: bool = True,
            check_battles: bool = False,
            check_data: bool = False,
            check_meta: bool = False
            ) -> dict:
        """
        Asynchronously handles the response from the API and returns the data as a dictionary.

        Args:
            response (aiohttp.ClientResponse): The response object received from the API.
            check_data_status (bool, optional): Flag to indicate whether to check the status of the data. Defaults to True.

        Raises:
            api_exceptions.APIError: Raised if the response status is not 200 or the data status is not 'ok'.
            api_exceptions.NeedMoreBattlesError: Raised if the number of battles is less than 100 (Optional).
            api_exceptions.RequestsLimitExceeded: Raised if the request limit is exceeded.
            api_exceptions.EmptyDataError: Raised if the data is empty.
            api_exceptions.APISourceNotAvailable: Raised if the API source is not available (code 504).
        Returns:
            dict: The data returned from the API as a dictionary.
        """
        if response.status != 200:
            _log.error(f'Error get data, bad response code: {response.status}')
            raise api_exceptions.APIError()
        
        data = await response.text()
        data = json.loads(data)
        if response.status == 504:
            raise api_exceptions.APISourceNotAvailable()

        if check_data_status:
            if data['status'] != 'ok':
                if data['error']['message'] == 'REQUEST_LIMIT_EXCEEDED':
                    _log.warning(f'Ingnoring Exception caused by API: Request Limit Exceeded')
                    raise api_exceptions.RequestsLimitExceeded('Rate Limit Exceeded')
                    
                _log.error(f'Error get data, bad response status: {data}')
                raise api_exceptions.APIError(f'Error get data, bad response status: {data}')

        if check_data:
            if data['data'] == None:
                _log.error(
                    f'API Returned empty `data` section'
                    f'Data: {data}'
                )
                raise api_exceptions.EmptyDataError(f'API Returned empty `data` section')
                
            elif data['data'][list(data['data'].keys())[0]] == None:
                _log.error(
                    f'API Returned empty `data` section'
                    f'Data: {data}'
                )
                raise api_exceptions.EmptyDataError(f'API Returned empty `data` section')
        
        if check_meta:
            if data['meta']['count'] == 0:
                _log.error(
                    f'API Returned `count 0`'
                    f'Data: {data["meta"]}'
                )
                raise api_exceptions.NoPlayersFound()
            
        if check_battles:
            if data['data'][list(data['data'].keys())[0]]['statistics']['all']['battles'] < 100:
                _log.error(f'Need more battles')
                raise api_exceptions.NeedMoreBattlesError()
      
        return data

    def _get_url_by_reg(self, reg: str):
        reg = self._reg_normalizer(reg)
        match reg:
            case 'ru':
                return _config.game_api.reg_urls.ru
            case 'eu':
                return _config.game_api.reg_urls.eu
            case 'asia':
                return _config.game_api.reg_urls.asia
            case 'com':
                return _config.game_api.reg_urls.na
            case _:
                raise api_exceptions.UncorrectRegion(f'Uncorrect region: {reg}')
    
    def get_players_callback(self, task: asyncio.Task) -> PlayerStats:
        self._palyers_stats.append(task.result())
        
            
    async def get_players_stats(self, players_id: list[int], region: str) -> list[PlayerStats | bool]:
        """
        Retrieves the statistics of multiple players based on their IDs and region.

        Parameters:
            players_id (list[int]): A list of player IDs.
            region (str): The region of the players.

        Returns:
            list[PlayerStats | bool]: A list of PlayerStats objects representing the statistics of each player. If an error occurs during the retrieval, a boolean value indicating the success of the operation is returned.
        """
        self._palyers_stats = []
        async with aiohttp.ClientSession() as session:
            async with asyncio.TaskGroup() as tg:
                for i in players_id:
                    tg.create_task(self._get_players_stats(i, region, session))
        
        return self._palyers_stats
                
    async def _get_players_stats(self, player_id: int, region: str, session: aiohttp.ClientSession) -> None:
        """
        Asynchronously gets the player stats for a given player ID and region.

        Parameters:
            player_id (int): The ID of the player.
            region (str): The region of the player.
            session (aiohttp.ClientSession): The HTTP session for making requests.

        Returns:
            None
        """
        await self.rate_limiter.wait()
        
        url_get_stats = insert_data(
            _config.game_api.urls.get_stats,
            {
                'reg_url' : self._get_url_by_reg(region),
                'app_id': self._get_id_by_reg(region),
                'player_id': player_id
            }
        )
        async with session.get(url_get_stats, verify_ssl=False) as response:
            try:
                data = await self.response_handler(response, check_battles=False, check_data=True)
            except api_exceptions.EmptyDataError:
                _log.debug(f'Error get player stats\n{traceback.format_exc()}')
                self._palyers_stats.append(False)
            except api_exceptions.APIError:
                _log.debug(f'Error get player stats\n{traceback.format_exc()}')
                self._palyers_stats.append(False)
            else:
                account_id = list(data['data'].keys())[0]
                data['data'] = data['data'][account_id]
                self._palyers_stats.append(PlayerStats.model_validate(data))

    async def retry_callback(self):
        _log.debug('Task failed, retrying...')

    @retry(
        expected_exception=(
            api_exceptions.RequestsLimitExceeded,
            api_exceptions.APISourceNotAvailable
        ),
        attempts=3,
        on_exception=retry_callback
    )
    async def get_tankopedia(self, region: str = 'ru') -> dict:
        """
        Get tankopedia data.

        Args:
            region (str, optional): The region for which to get the tankopedia data. Defaults to 'ru'.

        Returns:
            dict: The tankopedia data.

        """
        _log.debug('Get tankopedia data')
        url_get_tankopedia = (
            f'https://{self._get_url_by_reg(region)}/wotb/encyclopedia/vehicles/'
            f'?application_id={self._get_id_by_reg(region)}&language=en&fields='
            f'-description%2C+-engines%2C+-guns%2C-next_tanks%2C+-prices_xp%2C+'
            f'-suspensions%2C+-turrets%2C+-cost%2C+-default_profile%2C+-modules_tree%2C+-images'
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url_get_tankopedia, verify_ssl=False) as response:
                    data = await self.response_handler(response, False)

                    return data
        except client_exceptions.ClientConnectionError:
            raise api_exceptions.APIError('Client Exception Occurred')
                
    @retry(
            expected_exception=(
                api_exceptions.RequestsLimitExceeded,
                api_exceptions.APISourceNotAvailable
            ),
            attempts=3,
            on_exception=retry_callback
    )
    async def check_and_get_player(self, nickname: str, region: str, dicrord_id: int) -> DBPlayer | None:
        """
        Check a player's information.

        Args:
            nickname (str): The player's nickname.
            region (str): The player's region.

        Raises:
            RequestsLimitExceeded: If the request limit is exceeded.
            SourceNotAvailable: If the source is not available.

        Returns:
            dict | None: The player's information or None if the player is not found.
        """
        url_get_id = (
            f'https://{self._get_url_by_reg(region)}/wotb/account/list/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&search={nickname}'
            f'&type={"exact" if self.exact else "startswith"}'
        )

        region = self._reg_normalizer(region)
        async with aiohttp.ClientSession() as session:
            await self.rate_limiter.wait()
            async with session.get(url_get_id, verify_ssl=False) as response:
                try:
                    data = await self.response_handler(response, check_meta=True)
                    data = data['data'][0]
                    db_palyer = {
                        'nickname': data['nickname'],
                        'game_id': data['account_id'],
                        'region': region,
                        'id': dicrord_id,
                        'image_settings': ImageSettings().model_dump()
                    }
                except Exception as e:
                    _log.debug(f'Error check player\n{traceback.format_exc()}')
                    raise e
                
            url_get_stats = (
                f'https://{self._get_url_by_reg(region)}/wotb/account/info/'
                f'?application_id={self._get_id_by_reg(region)}'
                f'&account_id={db_palyer["game_id"]}'
                f'&fields=-statistics.clan'
            )
            await self.rate_limiter.wait()
            async with session.get(url_get_stats, verify_ssl=False) as response:
                try:
                    await self.response_handler(response, check_battles=True, check_data=True)
                except Exception as e:
                    _log.debug(f'Error check player\n{traceback.format_exc()}')
                    raise e
                else:
                    return DBPlayer.model_validate(db_palyer)
            
    def done_callback(self, task: asyncio.Task):
        pass

    async def get_stats(
        self, 
        region: str = None,
        game_id: int | None = None, 
        search: str | None = None, 
        exact: bool = True, 
        raw_dict: bool = False) -> PlayerGlobalData:
        """
        Asynchronously retrieves player statistics for a game. Optionally filters by game ID, player search string, and region.

        Parameters:
        - region (str): The region to which the player belongs.
        - game_id (int | None): Optional game identifier to filter the player stats.
        - search (str | None): Optional search string for a player's nickname.
        - exact (bool): Whether to perform an exact match on the player's nickname. Defaults to True.
        - raw_dict (bool): Whether to return the player's stats as a raw dictionary. Defaults to False.

        Returns:
        - PlayerGlobalData: An object containing normalized player statistics data or a raw dictionary if raw_dict is True.
        
        The function performs the following steps:
        - Validates the 'search' and 'region' parameters.
        - Initiates an asynchronous session and collects various player stats.
        - Normalizes and formats the collected data.
        - Returns the player statistics in the desired format.
        """
        need_caching: bool = False
        cahed_data = self.cache.get(((str(game_id), region)))
        if cahed_data is not None:
            data = PlayerGlobalData.model_validate(cahed_data)
            data.from_cache = True
            return get_normalized_data(data)
        else:
            need_caching = True
        
        self.exact = exact
        self.raw_dict = raw_dict

        self.start_time = time()

        player = await self.get_player(region=region, nickname=search, game_id=game_id)
        self.player['id'] = player['account_id']

        tasks = [
            self.get_player_stats,
            self.get_player_clan_stats,
            self.get_player_achievements,
            self.get_player_tanks_stats
        ]
        task_names = [
            'get_player_stats',
            'get_player_clan_stats',
            'get_player_achievements',
            'get_player_tanks_stats'
        ]

        default_params = {"account_id": player['account_id'], "region": region}
        self.player, self.player_stats = {}, {}
        async with aiohttp.ClientSession() as self.session:
            async with asyncio.TaskGroup() as tg:
                for i, task in enumerate(tasks):
                    self.create_task(tg, task_names[i], task, default_params)
            
        self.player['timestamp'] = int(datetime.now().timestamp())
        self.player['end_timestamp'] = int(
            datetime.now().timestamp() +
            _config.session.ttl
        )
        self.player['id'] = player['account_id']
        self.player['region'] = self._reg_normalizer(region)
        self.player['lower_nickname'] = player['nickname'].lower()
        self.player['timestamp'] = int(datetime.now().timestamp())
        self.player['end_timestamp'] = int(datetime.now().timestamp()) + _config.session.ttl
        self.player['nickname'] = player['nickname']
        self.player['data'] = self.player_stats

        player_stats = PlayerGlobalData.model_validate(self.player)

        if self.raw_dict:
            return player_stats.model_dump()
        
        if need_caching:
            player_stats.from_cache = False
            self.cache.add((str(game_id), region), player_stats.model_dump())

        return get_normalized_data(player_stats)

    def create_task(
            self, 
            tg: asyncio.TaskGroup, 
            task_name: str, 
            task, 
            params: Dict[str, Union[str, int]]
            ) -> None:
        task = tg.create_task(task(**params))
        task.set_name(task_name)
        task.add_done_callback(self.done_callback)

    @retry(
            expected_exception=(
                api_exceptions.RequestsLimitExceeded,
                api_exceptions.APISourceNotAvailable
            ),
            attempts=3,
            on_exception=retry_callback
    )
    async def get_player(
        self, 
        region: str, 
        nickname: str | None = None, 
        game_id: int | None = None) -> dict:
        """
        Retrieves the account ID of a player by their nickname and region.

        Args:
            region (str): The region of the player.
            nickname (str): The nickname of the player.
            **kwargs: Additional keyword arguments.

        Returns:
            int: The account ID of the player.

        Raises:
            api_exceptions.RequestsLimitExceeded: If the API requests limit is exceeded.
            api_exceptions.SourceNotAvailable: If the API source is not available.
            api_exceptions.UncorrectName: If the player name is incorrect.
            api_exceptions.MoreThanOnePlayerFound: If more than one player is found with the given nickname.
            api_exceptions.NoPlayersFound: If no players are found with the given nickname."""
            
        url_get_id = insert_data(
            _config.game_api.urls.get_id,
            {   
                'app_id'  : self._get_id_by_reg(region),
                'reg_url' : self._get_url_by_reg(region),
                'nickname': nickname,
                'search_type' : 'exact' if self.exact else 'startswith',
            }
        )

        await self.rate_limiter.wait()
        async with aiohttp.ClientSession() as self.session:
            if game_id is None:
                async with self.session.get(url_get_id, verify_ssl=False) as response:
                    data = await self.response_handler(response)

                    if data['status'] == 'error':
                        match data['error']['code']:
                            case 407 | 402:
                                raise api_exceptions.UncorrectName()
                    
                    game_id: int = data['data'][0]['account_id']
                    
            url_get_stats = insert_data(
            _config.game_api.urls.get_stats,
                {
                    'app_id'  : self._get_id_by_reg(region),
                    'reg_url' : self._get_url_by_reg(region),
                    'player_id' : game_id
                }
            )
            
            async with self.session.get(url_get_stats, verify_ssl=False) as response:
                data = await self.response_handler(response, check_battles=True)
                return data['data'][str(game_id)]
            
    @retry(
            expected_exception=(
                api_exceptions.RequestsLimitExceeded,
                api_exceptions.APISourceNotAvailable
            ),
            attempts=3,
            on_exception=retry_callback
    )
    async def get_player_battles(self, region: str, account_id: str, **kwargs) -> int:
        """
        Retrieves the number of battles played by a player.

        Args:
            region (str): The region of the player's account.
            account_id (str): The ID of the player's account.
            **kwargs: Additional keyword arguments.

        Returns:
            int: The number of battles played by the player.
        """
        url_get_battles = (
            f'https://{self._get_url_by_reg(region)}/wotb/account/info/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&account_id={account_id}'
            f'&fields=-statistics.clan'
        )
        await self.rate_limiter.wait()
        async with aiohttp.ClientSession() as sesison:
            async with sesison.get(url_get_battles, verify_ssl=False) as response:
                data = await self.response_handler(response)

        return data['data'][str(account_id)]['statistics']['all']['battles']
    

    @retry(
            expected_exception=(
                api_exceptions.RequestsLimitExceeded,
                api_exceptions.APISourceNotAvailable
            ),
            attempts=3,
            on_exception=retry_callback
    )
    async def get_player_stats(self, region: str, account_id: str) -> PlayerStats:
        """
        Retrieves the player statistics for a given region and account ID.
        
        Args:
            region (str): The region of the player (e.g. "NA", "EU", "ASIA").
            account_id (str): The ID of the player's account.
            **kwargs: Additional keyword arguments to be passed.
        
        Returns:
            PlayerStats: An object containing the player's statistics.
        
        Raises:
            RequestsLimitExceeded: If the API requests limit is exceeded.
            SourceNotAvailable: If the API source is not available.
            EmptyDataError: If the "battles" field is not present in the output data.
            NeedMoreBattlesError: If the player has less than 100 battles.
        """
        _log.debug('Get main stats started')
        url_get_stats = insert_data(
            _config.game_api.urls.get_stats,
            {
                'app_id'  : self._get_id_by_reg(region),
                'reg_url' : self._get_url_by_reg(region),
                'player_id' : account_id
            }
        )

        await self.rate_limiter.wait()
        async with self.session.get(url_get_stats, verify_ssl=False) as response:
            data = await self.response_handler(response, check_battles=True)

        data['data'] = data['data'][str(account_id)]

        data = PlayerStats.model_validate(data)

        self.player_stats['statistics'] = data.data.statistics

    @retry(
            expected_exception=(
                api_exceptions.RequestsLimitExceeded,
                api_exceptions.APISourceNotAvailable
            ),
            attempts=3,
            on_exception=retry_callback
    )
    async def get_player_achievements(self, region: str, account_id: str) -> None:
        """
        Retrieves the achievements of a player.

        Args:
            region (str): The region of the player.
            account_id (str): The ID of the player's account.

        Returns:
            None
        """
        _log.debug('Get achievements started')
        url_get_achievements = (
            f'https://{self._get_url_by_reg(region)}/wotb/account/achievements/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&fields=-max_series&account_id={account_id}'
        )

        await self.rate_limiter.wait()
        async with self.session.get(url_get_achievements, verify_ssl=False) as response:
            data = await self.response_handler(response)

        self.player_stats['achievements'] = Achievements.model_validate(data['data'][str(account_id)]['achievements'])


    @retry(
            expected_exception=(
                api_exceptions.RequestsLimitExceeded,
                api_exceptions.APISourceNotAvailable
            ),
            attempts=3,
            on_exception=retry_callback
    )
    async def get_player_clan_stats(self, region: str, account_id: str | int) -> None:
        """
        Retrieves clan statistics for a player.

        Args:
            region (str): The region of the player.
            account_id (str | int): The account ID of the player.

        Returns:
            None

        Raises:
            api_exceptions.RequestsLimitExceeded: If the API requests limit is exceeded.
            api_exceptions.SourceNotAvailable: If the API source is not available.
        """
        _log.debug('Get clan stats started')
        url_get_clan_stats = (
            f'https://{self._get_url_by_reg(region)}/wotb/clans/accountinfo/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&account_id={account_id}'
            f'&extra=clan'
        )

        await self.rate_limiter.wait()
        async with self.session.get(url_get_clan_stats, verify_ssl=False) as response:
            data = await self.response_handler(response)

        if data['data'][str(account_id)] is None:
            self.player_stats['clan_tag'] = None
            self.player_stats['clan_stats'] = None
            return
        
        data['data'] = data['data'][str(account_id)]


        data = ClanStats.model_validate(data)

        self.player_stats['clan_tag'] = data.data.clan.tag
        self.player_stats['clan_stats'] = data.data.clan

    @retry(
            expected_exception=(
                api_exceptions.RequestsLimitExceeded,
                api_exceptions.APISourceNotAvailable
            ),
            attempts=3,
            on_exception=retry_callback
    )
    async def get_player_tanks_stats(self, region: str, account_id: str,  **kwargs):
        """
        Retrieves the statistics of the tanks owned by a player.

        Args:
            region (str): The region of the player.
            account_id (str): The account ID of the player.
            nickname (str): The nickname of the player.
            **kwargs: Additional keyword arguments.

        Returns:
            None

        Raises:
            api_exceptions.RequestsLimitExceeded: If the requests limit has been exceeded.
            api_exceptions.SourceNotAvailable: If the data source is not available.
        """
        _log.debug('Get player tank stats started')
        url_get_tanks_stats = (
            f'https://{self._get_url_by_reg(region)}/wotb/tanks/stats/'
            f'?application_id={self._get_id_by_reg(region)}'
            f'&account_id={account_id}'
        )

        await self.rate_limiter.wait()
        async with self.session.get(url_get_tanks_stats, verify_ssl=False) as response:
            data = await self.response_handler(response)

        tanks_stats: dict[str, TankStats] = {}

        for tank in data['data'][str(account_id)]:
            tanks_stats[str(tank['tank_id'])] = TankStats.model_validate(tank)
            
        self.player_stats['tank_stats'] = tanks_stats
