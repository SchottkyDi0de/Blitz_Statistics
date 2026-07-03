from datetime import datetime, timedelta
from asyncio import sleep
from types import NoneType

import pytz
import motor.motor_asyncio
from bson.codec_options import CodecOptions

from lib.data_classes.api.api_data import PlayerGlobalData
from lib.data_classes.db_player import (
    BadgesEnum,
    DBPlayer,
    HookStats,
    ImageSettings,
    SessionSettings, 
    StatsViewSettings, 
    WidgetSettings,
    GameAccount,
    Profile,
    SessionStatesEnum,
    AccountSlotsEnum,
    UsedCommand,
    SlotAccessState
)
from lib.data_classes.db_player_old import DBPlayerOld
from lib.exceptions import database
from lib.logger.logger import get_logger
from lib.settings.settings import Config, EnvConfig
from lib.utils.calculate_exp import exp_add
from lib.utils.singleton_factory import singleton
from lib.utils.validate_badges import validate_badge

_config = Config().get()
_log = get_logger(__file__, 'PlayersDBLogger', 'logs/players_db.log')


@singleton
class PlayersDB:
    def __init__(self) -> None:
        self.client = motor.motor_asyncio.AsyncIOMotorClient(EnvConfig.MONGODB_URI)
        self.db = self.client['PlayersDB']
        self.collection = self.db.get_collection('players', codec_options=CodecOptions(tz_aware=True, tzinfo=pytz.utc))
    
    async def _multi_args_member_checker(self, member_id: int | str | None = None, member: DBPlayer | None = None, raise_error: bool = True) -> DBPlayer:
        """
        Check if the given member ID and member object are valid and return the appropriate member object.

        Args:
            member_id (int): The ID of the member.
            member (DBPlayer): The member object.

        Raises:
            ValueError: If neither member ID nor member object is provided.

        Returns:
            DBPlayer: The member object if it is not None, otherwise the member object retrieved from the database using the member ID.

        """
        if (member_id is None) and (member is None):
            raise ValueError('You must provide either id or member')
        
        if member is None:
            member = await self.get_member(member_id, raise_error=raise_error)
            if isinstance(member, bool):
                return None
            else:
                return member
        else:
            return member
        
    async def create_index_for_id(self):
        """
        Asynchronously creates an index on the 'id' field of the collection.

        This function creates a unique index on the 'id' field of the collection. The index is used to improve the performance of queries that involve the 'id' field.

        Parameters:
            self (PlayersDB): The instance of the PlayersDB class.

        Returns:
            None
            
        Note:
            Use one time only.
        """
        await self.collection.create_index({'id': 1}, unique=True)
        
    async def get_all_members_count(self) -> int:
        """
        Asynchronously retrieves the count of all documents in the collection.

        This function uses the `count_documents` method of the `collection` attribute to 
        retrieve the count of all documents in the collection. The count is obtained by 
        passing an empty filter `{}` to the method.

        Returns:
            int: The count of all documents in the collection.
        """
        return await self.collection.count_documents({})
    
    async def count_sessions(self) -> int:
        """
        Asynchronously counts the total number of sessions for all members in the collection.
        
        This function iterates over all documents in the collection, retrieves the member object,
        and checks each of their used slots for last stats. The count of sessions is incremented
        for each slot with last stats.
        
        Parameters:
            self (PlayersDB): The instance of the PlayersDB class.
        
        Returns:
            int: The total count of sessions for all members in the collection.
        """
        sessions = 0
        cursor = self.collection.find({})

        while cursor.alive:
            member = DBPlayer.model_validate(await cursor.next())
            all_slots = await self.get_all_used_slots(member=member)
            for slot in all_slots:
                if await self.check_member_last_stats(member=member, slot=slot):
                    sessions += 1
        
        return sessions

    async def get_all_members_ids(self) -> list[int]:
        """
        Asynchronously retrieves a list of all unique member IDs from the collection.

        This function uses the `distinct` method of the `collection` attribute to retrieve
        a list of all unique values for the 'id' field in the collection. The result is a
        list of member IDs.

        Returns:
            list: A list of unique member IDs.
        """
        return await self.collection.distinct('id')
    
    async def set_member(self, slot: AccountSlotsEnum, member_id: int | str, game_account: GameAccount, slot_override: bool = False) -> None:
        """
        Sets a member's game account in the specified slot or creates a new member if it doesn't exist.

        Args:
            member_id (int | str): The ID of the member.
            game_account (GameAccount): The game account to set.
            slot (AccountSlotsEnum, optional): The slot to set the game account in. Defaults to AccountSlotsEnum.slot_1.
            slot_override (bool, optional): Whether to override the slot if it's not empty. Defaults to False.

        Raises:
            TypeError: If the slot is not an instance of AccountSlotsEnum.

        Returns:
            None
        """
        if not isinstance(slot, AccountSlotsEnum):
            raise TypeError(f'slot must be an instance of AccountSlotsEnum, not {slot.__class__.__name__}')
        
        member_id = int(member_id)
        member = await self.check_member_exists(member_id=member_id, raise_error=False, get_if_exist=True)
        
        if not isinstance(member, bool):
            await self.check_access_to_slot(slot, member=member)
            slot_is_empty = await self.check_slot_empty(slot, member=member, raise_error=False)
            if slot_is_empty or slot_override:
                await self.collection.update_one(
                    {'id': member_id},
                    {'$set': {f'game_accounts.{slot.name}': game_account.model_dump()}}
                )
        else:
            await self.collection.insert_one({
                'id': member_id,
                'lang' : None,
                'image' : None,
                'game_accounts':{
                    'slot_1': game_account.model_dump(),
                    'slot_2': None,
                    'slot_3': None,
                    'slot_4': None,
                    'slot_5': None
                },
                'profile': Profile().model_dump(),
                'current_game_account': AccountSlotsEnum.slot_1.name
            })
        
            
    async def get_member(self, member_id: int | str, raise_error: bool = True) -> DBPlayer | bool:
        """
        Asynchronously retrieves a member from the database based on their ID.

        Args:
            member_id (int | str): The ID of the member to retrieve.

        Returns:
            DBPlayer: The member object if it exists in the database, None otherwise.
        """
        member: DBPlayer = await self.check_member_exists(member_id=member_id, get_if_exist=True, raise_error=raise_error)
        return member
    
    async def get_slot_state(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> SlotAccessState:
        """
        Asynchronously retrieves the state of a game slot for a given member.

        Args:
            slot (AccountSlotsEnum): The game slot to retrieve the state for.
            member_id (int | str | None): The ID of the member to retrieve the slot state for. Defaults to None.
            member (DBPlayer | None): The member object to retrieve the slot state for. Defaults to None.

        Returns:
            SlotAccessState: The state of the game slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        
        if slot is None:
            slot = await self.get_current_game_slot(member=member)
            
        if not isinstance(slot, AccountSlotsEnum):
            _log.warning(f'slot must be an instance of AccountSlotsEnum, not {slot.__class__.__name__}')
            return SlotAccessState.invalid_slot
        
        if slot.value > 2 and not await self.check_premium(member=member):
            return SlotAccessState.locked_slot
        
        try:
            slot_data = getattr(member.game_accounts, slot.name)
        except AttributeError:
            return SlotAccessState.empty_slot
        else:
            if slot_data is None:
                return SlotAccessState.empty_slot
        
            return SlotAccessState.used_slot
    
    def get_slot_state_sync(self, slot: AccountSlotsEnum, member: DBPlayer) -> SlotAccessState:
        """
        Synchronously retrieves the state of a game slot for a given member.

        Args:
            slot (AccountSlotsEnum): The game slot to retrieve the state for.
            member (DBPlayer): The member object to retrieve the slot state for.

        Returns:
            SlotAccessState: The state of the game slot.
        """
        if not isinstance(slot, AccountSlotsEnum):
            _log.warning(f'slot must be an instance of AccountSlotsEnum, not {slot.__class__.__name__}')
            return SlotAccessState.invalid_slot
        
        if slot.value > 2 and not member.profile.premium:
            return SlotAccessState.locked_slot
        
        try:
            slot_data = getattr(member.game_accounts, slot.name)
        except AttributeError:
            return SlotAccessState.empty_slot
        else:
            if slot_data is None:
                return SlotAccessState.empty_slot
        
            return SlotAccessState.used_slot
        
        
    async def validate_slot(
        self, 
        slot: AccountSlotsEnum | None, 
        member_id: int | str | None = None, 
        member: DBPlayer | None = None,
        set_if_locked: bool = False,
        empty_allowed: bool = False
        ) -> AccountSlotsEnum:
        """
        Asynchronously validates a game slot for a given member.

        Args:
            slot (AccountSlotsEnum | None): The game slot to validate. If None, the current game slot will be used.
            member_id (int | str | None, optional): The ID of the member to validate the slot for. Defaults to None.
            member (DBPlayer | None, optional): The member object to validate the slot for. Defaults to None.
            set_if_locked (bool, optional): Whether to set the current account to slot_1 if the slot is locked. Defaults to False.
            empty_allowed (bool, optional): Whether to allow empty slots. Defaults to False.

        Returns:
            AccountSlotsEnum: The validated game slot.

        Raises:
            TypeError: If the slot is not an instance of AccountSlotsEnum.
            ValueError: If the slot is invalid.
            database.PremiumSlotAccessAttempt: If the slot is locked and set_if_locked is False.
            database.SlotIsEmpty: If the slot is empty and empty_allowed is False.
            database.SlotIsNotEmpty: If the slot is used and empty_allowed is True.
        """
        
        if not isinstance(slot, AccountSlotsEnum):
            raise TypeError(f'slot must be an instance of AccountSlotsEnum, not {slot.__class__.__name__}')
        
        slot_state = await self.get_slot_state(slot=slot, member_id=member_id, member=member)
        if slot_state == SlotAccessState.invalid_slot:
            raise ValueError(f'Invalid slot {slot}')
        elif slot_state == SlotAccessState.locked_slot and not set_if_locked:
            raise database.PremiumSlotAccessAttempt
        elif slot_state == SlotAccessState.locked_slot and set_if_locked:
            await self.set_current_account(member_id=member.id, slot=AccountSlotsEnum.slot_1)
            return AccountSlotsEnum.slot_1
        elif slot_state == SlotAccessState.empty_slot and not empty_allowed:
            raise database.SlotIsEmpty
        elif slot_state == SlotAccessState.used_slot and empty_allowed:
            raise database.SlotIsNotEmpty
        else:
            return slot
        
    async def get_game_account(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> GameAccount:
        """
        Asynchronously retrieves the game account associated with the specified member and slot.

        Args:
            slot (AccountSlotsEnum): The slot of the game account to retrieve.
            member_id (int | str | None, optional): The ID of the member. Defaults to None.
            member (DBPlayer | None, optional): The member object. Defaults to None.

        Returns:
            GameAccount: The game account associated with the specified member and slot.

        Raises:
            database.SlotIsEmpty: If the member does not have a game account in the specified slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        game_account = getattr(member.game_accounts, slot.name)
        if game_account is None:
            _log.warn(f'Member {member_id} has no game account in slot {slot.name}')
            raise database.SlotIsEmpty(f'Member {member_id} has no game account in slot {slot.name}')
        else:
            return game_account
    
    async def delete_member(self, member_id: int | str) -> None:
        """
        Asynchronously deletes a member from the database based on their ID.

        Args:
            member_id (int | str): The ID of the member to delete.

        Returns:
            None: This function does not return anything.
        """
        await self.collection.delete_one({'id': member_id})
        
    async def check_member_exists(self, member_id: int | str, get_if_exist: bool = False, raise_error: bool = True) -> bool | DBPlayer:
        """
        Asynchronously checks if a player with the given ID exists in the database.

        Parameters:
            id (int | str): The ID of the player to check.
            get_if_exist (bool, optional): If True, returns the player object if it exists. Defaults to False.
            raise_error (bool, optional): If True, raises a MemberNotFound exception if the player does not exist. Defaults to True.

        Returns:
            bool | DBPlayer: If get_if_exist is False, returns True if the player exists, False otherwise.
            If get_if_exist is True, returns the player object if it exists, False otherwise.

        Raises:
            MemberNotFound: If raise_error is True and the player does not exist.
        """
        member_id = int(member_id)
        result = await self.collection.find_one({'id': member_id})
        
        if raise_error and (result is None):
            _log.info(f'Player with id {member_id} not found')
            raise database.MemberNotFound()
        
        if get_if_exist:
            if result is not None:
                player = DBPlayer.model_validate(result)
                return player
            else:
                return False
        else:
            return True if result is not None else False
    
    async def check_access_to_slot(
        self, 
        slot: AccountSlotsEnum, 
        member_id: int | str = None, 
        member: DBPlayer = None,
        auto_set_if_locked: bool = False) -> None:
        """
        Check if a member has access to a specific slot.

        Args:
            slot (AccountSlotsEnum): The slot to check access for.
            member_id (int | str, optional): The ID of the member. Defaults to None.
            member (DBPlayer, optional): The member object. Defaults to None.

        Raises:
            database.PremiumSlotAccessAttempt: If the member is not premium and tries to access a premium slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        premium = await self.check_premium(member_id, member)
        
        if slot.value > 2:
            if not premium and auto_set_if_locked:
                await self.set_current_account(member_id=member.id, slot=AccountSlotsEnum.slot_1, validate=False)
            elif not premium and not auto_set_if_locked:
                _log.info(f'Member is not premium and tried to access premium slot {slot.value}')
                raise database.PremiumSlotAccessAttempt(f'Member is not premium and tried to access premium slot {slot.value}')
            else:
                pass
            
    async def check_slot_empty(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None, raise_error: bool = True) -> bool:
        """
        Check if the specified slot is empty for a given member.

        Args:
            slot (AccountSlotsEnum): The slot to check for emptiness.
            member_id (int | str, optional): The ID of the member. Defaults to None.
            member (DBPlayer, optional): The member object. Defaults to None.
            raise_error (bool, optional): Whether to raise an exception if the slot is not empty.
            Defaults to True.

        Returns:
            bool: True if the slot is empty, False otherwise.

        Raises:
            database.SlotIsNotEmpty: If the slot is not empty and raise_error is True.
        """
        member = await self._multi_args_member_checker(member_id, member)
        
        if getattr(member.game_accounts, slot.name) is not None:
            if raise_error:
                _log.warn(f'Member tried to access not empty slot {slot.value}')
                raise database.SlotIsNotEmpty()
            else:
                return False
        else:
            return True
        
    async def unset_premium(self, member_id: int | str) -> None:
        """
        Unsets the premium status of a member in the database.

        Args:
            id (int | str): The ID of the member.

        Returns:
            None

        Raises:
            None

        This function updates the 'profile.premium' and 'profile.premium_time' fields of the member with the given ID in the database. It sets 'profile.premium' to False and 'profile.premium_time' to None, effectively unsetting the premium status of the member.
        """
        member = await self.check_member_exists(member_id, get_if_exist=True)
        curr_slot = await self.get_current_game_slot(member=member)
        if curr_slot.value > 2:
            await self.set_current_account(member_id=member.id, slot=AccountSlotsEnum.slot_1, validate=False)
        
        await self.collection.update_one(
            {'id': member.id}, 
            {'$set': {'profile.premium': False, 'profile.premium_time': None}}
        )
        
    async def set_premium(self, member_id: int | str, end_time: datetime | None) -> None:
        """
        Sets the premium status of a member in the database.

        Args:
            id (int | str): The ID of the member.
            end_time (datetime | None): The end time of the member's premium status. If None, the member will be set as premium indefinitely.

        Returns:
            None

        Raises:
            None

        This function updates the 'profile.premium' and 'profile.premium_time' fields of the member with the given ID in the database. If 'end_time' is None, the member will be set as premium indefinitely. Otherwise, the member will be set as premium until the specified 'end_time'.
        """
        _log.info(f'Setting premium for id {member_id}, end_time: {end_time}')
        end_time = datetime.now(pytz.utc) + timedelta(days=14) if end_time is None else end_time
        await self.collection.update_one(
            {'id': int(member_id)},
            {'$set': {'profile.premium': True, 'profile.premium_time': end_time}}
        )
        
    async def check_premium(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> bool:
        """
        Check if a member is premium or not.

        Args:
            member_id (int | str): The ID of the member. If None, the member object must be provided.
            member (DBPlayer): The member object. If None, the member_id must be provided.

        Returns:
            bool: True if the member is premium, False otherwise.

        Raises:
            ValueError: If neither member_id nor member is provided.

        This function checks if a member is premium or not. It takes either a member_id or a member object as input.
        If both are provided, the member_id is ignored. If neither is provided, a ValueError is raised.

        The function first checks if the member is premium by retrieving the member object using the member_id.
        If the member is premium, it checks if the premium_time is None. If it is None, the member is considered premium.
        If the premium_time is not None, it checks if the current datetime is before the premium_time. If it is, the member is considered premium.
        If the current datetime is after the premium_time, the member's premium status is unset and False is returned.

        If the member is not premium, False is returned.
        """
        # TODO: For the premium check to work, remove the return and uncomment the code below
        #
        # member = await self._multi_args_member_checker(member_id, member)
        
        # premium = member.profile.premium
        # premium_time = member.profile.premium_time
        
        # if premium:
        #     if premium_time is None:
        #         return True
        #     else:
        #         if datetime.now(pytz.utc) < premium_time:
        #             return True
        #         else:
        #             _log.debug(f'Unset premium for member {member.id}')
        #             await self.unset_premium(member.id)
        #             return False
        # else:
        #     return False
        
        return True

    async def get_current_game_account(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> GameAccount:
        """
        Asynchronously retrieves the current game account associated with the specified member.

        Args:
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            GameAccount: The current game account associated with the specified member.

        Raises:
            database.SlotIsEmpty: If the member does not have a game account in the current slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        game_account: GameAccount | None = getattr(member.game_accounts, member.current_game_account)
        if game_account is None:
            _log.warn(f'Member {member.id} has no game account in slot {member.current_game_account}')
            raise database.SlotIsEmpty(f'Member {member.id} has no game account in slot {member.current_game_account}')
        else:
            return game_account

    async def get_current_game_slot(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> AccountSlotsEnum:
        """
        Asynchronously retrieves the current game slot associated with the specified member.

        Args:
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            AccountSlotsEnum: The current game slot associated with the specified member.
        """
        member = await self._multi_args_member_checker(member_id, member)
        return AccountSlotsEnum[member.current_game_account]
        
    async def start_session(self, slot: AccountSlotsEnum, member_id: int | str, last_stats: PlayerGlobalData, session_settings: SessionSettings) -> None:
        """
        Starts a new session for a member in a specified game slot.

        Args:
            slot (AccountSlotsEnum): The game slot to start the session in.
            member_id (int | str): The ID of the member.
            last_stats (PlayerGlobalData): The last statistics of the member.
            session_settings (SessionSettings): The settings for the session.

        Returns:
            None: This function does not return anything.
        """
        member = await self.check_member_exists(member_id, get_if_exist=True)
        slot = await self.validate_slot(member=member, slot=slot)
        await self.collection.update_one(
            {'id': member_id},
            {'$set': 
                {
                    f'game_accounts.{slot.name}.last_stats': last_stats.model_dump(),
                    f'game_accounts.{slot.name}.session_settings': session_settings.model_dump(),
                }
            },
        )
    
    async def find_account_by_params(
            self,
            nickname: str,
            region: str,
            member_id: int | str | None = None,
            member: DBPlayer | None = None,
        ) -> GameAccount | None:
        """
        Asynchronously searches for a game account by nickname and region.

        Args:
            self: A reference to the current instance of the class.
            nickname (str): The nickname of the game account to search for.
            region (str): The region of the game account to search for.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            GameAccount | None: The game account associated with the specified nickname and region, or None if not found.
        """
        member = self._multi_args_member_checker(member_id, member)
        game_accounts = member.game_accounts
        used_slots: list[AccountSlotsEnum] = await self.get_all_used_slots(member=member)
        if used_slots is None:
            return None
        
        for slot in used_slots:
            if getattr(game_accounts, slot.name).nickname.lower() == nickname.lower():
                if getattr(game_accounts, slot.name).region == region:
                    return getattr(game_accounts, slot.name)
        
        return None
        
    async def get_session_settings(self, slot: AccountSlotsEnum, member_id: int | str, member: DBPlayer) -> SessionSettings:
        """
        Asynchronously retrieves the session settings for a specific game account slot.

        Args:
            self: A reference to the current instance of the class.
            slot (AccountSlotsEnum): The game account slot to retrieve session settings for.
            member_id (int | str): The ID of the member.
            member (DBPlayer): The member object.

        Returns:
            SessionSettings: The session settings for the specified game account slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        return getattr(member.game_accounts, slot.name).session_settings
    
    async def get_image_settings(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> ImageSettings:
        """
        Asynchronously retrieves the image settings for a specific game account slot.

        Args:
            self: A reference to the current instance of the class.
            slot (AccountSlotsEnum): The game account slot to retrieve image settings for.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            ImageSettings: The image settings for the specified game account slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        return getattr(member.game_accounts, slot.name).image_settings
    
    async def get_last_stats(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> PlayerGlobalData:
        """
        Asynchronously retrieves the last game statistics for a specific game account slot.

        Args:
            self: A reference to the current instance of the class.
            slot (AccountSlotsEnum): The game account slot to retrieve last statistics for.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            PlayerGlobalData: The last game statistics for the specified game account slot.

        Raises:
            database.LastStatsNotFound: If the member has no last statistics in the specified slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        last_stats = getattr(member.game_accounts, slot.name).last_stats
        if last_stats is None:
            _log.warn(f'Member {member.id} has no last stats in slot {slot.name}')
            raise database.LastStatsNotFound(f'Member {member.id} has no last stats in slot {slot.name}')
        else:
            return PlayerGlobalData.model_validate(last_stats)
        
    async def get_stats_view_settings(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> StatsViewSettings:
        """
        Asynchronously retrieves the stats view settings for a specific game account slot.

        Args:
            slot (AccountSlotsEnum): The game account slot to retrieve stats view settings for.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            StatsViewSettings: The stats view settings for the specified game account slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        return getattr(member.game_accounts, slot.name).stats_view_settings

    async def get_widget_settings(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> WidgetSettings:
        """
        Asynchronously retrieves the widget settings for a specific game account slot.

        Args:
            self: A reference to the current instance of the class.
            slot (AccountSlotsEnum): The game account slot to retrieve widget settings for.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            WidgetSettings: The widget settings for the specified game account slot.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        return getattr(member.game_accounts, slot.name).widget_settings
    
    async def stop_session(self, slot: AccountSlotsEnum, member_id: int | str) -> None:
        """
        Asynchronously stops a session for a specific game account slot.

        Args:
            self: A reference to the current instance of the class.
            slot (AccountSlotsEnum): The game account slot to stop the session for.
            member_id (int | str): The ID of the member.

        Returns:
            None: This function does not return anything.
        """
        slot = await self.validate_slot(member_id=member_id, slot=slot)
        await self.collection.update_one(
            {'id': member_id},
            {'$set': {f'game_accounts.{slot.name}.last_stats': None}}
        )
    
    async def check_member_last_stats(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None, premium_bypass: bool = False) -> bool:
        """
        Asynchronously checks the last stats of a member's game account slot.

        Args:
            slot (AccountSlotsEnum): The game account slot to check the last stats for.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.
            premium_bypass (bool): Whether to bypass premium checks. Defaults to False.

        Returns:
            bool: True if the last stats are valid, False otherwise.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        game_account: GameAccount = getattr(member.game_accounts, slot.name)
        last_stats = game_account.last_stats
        session_settings = game_account.session_settings
        if last_stats is None:
            return False
        else:
            if session_settings.last_get + timedelta(seconds=_config.session.ttl) < datetime.now(pytz.utc):
                await self.stop_session(slot=slot, member_id=member.id)
                return False
            else:
                return True
            
    async def session_restart_needed(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> bool:
        """
        Asynchronously checks if a session restart is needed for a specific game account slot.

        Args:
            slot (AccountSlotsEnum): The game account slot to check.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            bool: True if a session restart is needed, False otherwise.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        game_account: GameAccount = getattr(member.game_accounts, slot.name)
        session_settings = game_account.session_settings
        if not session_settings.is_autosession:
            return False
        elif session_settings.time_to_restart < datetime.now(pytz.utc):
            return True
        else:
            return False
        
    async def validate_session(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None, premium_bypass: bool = False) -> SessionStatesEnum:
        """
        Asynchronously validates the session state for a specific game account slot.

        Args:
            slot (AccountSlotsEnum): The game account slot to validate the session for.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.
            premium_bypass (bool): Whether to bypass premium checks. Defaults to False.

        Returns:
            SessionStatesEnum: The current state of the session (NOT_STARTED, RESTART_NEEDED, or NORMAL).
        """
        member = await self._multi_args_member_checker(member_id, member)
        last_stats = await self.check_member_last_stats(slot, member=member, premium_bypass=premium_bypass)
        if not last_stats:
            return SessionStatesEnum.NOT_STARTED
        elif await self.session_restart_needed(slot=slot, member=member):
            return SessionStatesEnum.RESTART_NEEDED
        else:
            return SessionStatesEnum.NORMAL
        
    async def update_session(
            self,
            slot: AccountSlotsEnum,
            member_id: int | str,
            session_settings: SessionSettings,
            last_stats: PlayerGlobalData, 
        ) -> None:
        """
        Asynchronously updates the session settings and last stats for a specific game account slot.

        Args:
            slot (AccountSlotsEnum): The game account slot to update the session for.
            member_id (int | str): The ID of the member.
            session_settings (SessionSettings): The session settings to update.
            last_stats (PlayerGlobalData): The last stats to update.

        Returns:
            None
        """
        member = await self._multi_args_member_checker(member_id, None)
        curr_slot = await self.get_current_game_slot(member_id, member) if slot is None else slot
        restart_time = session_settings.time_to_restart + timedelta(days=1)
        session_settings.time_to_restart = restart_time
        await self.collection.update_one(
            {'id': member_id},
            {'$set': 
                {
                    f'game_accounts.{curr_slot.name}.last_stats': last_stats.model_dump(), 
                    f'game_accounts.{curr_slot.name}.session_settings': session_settings.model_dump(),
                }
            }
        )
        
    async def get_all_used_slots(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> list[AccountSlotsEnum]:
        """
        Asynchronously retrieves a list of all used game account slots for a specific member.

        Args:
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            list[AccountSlotsEnum]: A list of used game account slots.
        """
        member = await self._multi_args_member_checker(member_id, member)
        premium_user = await self.check_premium(member_id, member)
        slots = []
        
        for iter_slot in AccountSlotsEnum:
            if iter_slot.value > 2 and not premium_user:
                break
            
            if not await self.check_slot_empty(member=member, slot=iter_slot, raise_error=False):
                slots.append(iter_slot)
                
        return slots
    
    async def get_lang(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> str | None:
        """
        Asynchronously retrieves the language of a specific member.

        Args:
            member_id (int | str | None): The ID of the member.
            member (DBPlayer | None): The member object.

        Returns:
            str | None: The language of the member if it exists, otherwise None.
        """
        member = await self._multi_args_member_checker(member_id, member, raise_error=False)
        return DBPlayer.model_validate(member).lang if member is not None else None
    
    async def set_lang(self, member_id: int | str, lang: str | None) -> None:
        """
        Asynchronously sets the language of a member in the database.

        Args:
            member_id (int | str): The ID of the member.
            lang (str | None): The language to set. If None, the language field will be set to None.

        Returns:
            None: This function does not return anything.

        This function updates the 'lang' field of the member with the given ID in the database. If the language is None, it sets the language field to None.
        """
        await self.collection.update_one(
            {'id': int(member_id)},
            {'$set': {'lang': lang}}
        )
    
    async def check_member_is_verified(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> bool:
        """
        Asynchronously checks if a member's game account slot is verified.

        Args:
            slot (AccountSlotsEnum): The game account slot to check for verification.
            member_id (int | str | None): The ID of the member. Defaults to None.
            member (DBPlayer | None): The member object. Defaults to None.

        Returns:
            bool: True if the member's game account slot is verified, False otherwise.
        """
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        return getattr(member.game_accounts, slot.name).verified
    
    async def set_member_lock(self, slot: AccountSlotsEnum, member_id: int | str, lock: bool) -> None:
        """
        Asynchronously sets the lock status of a member's game account slot in the database.

        Args:
            slot (AccountSlotsEnum): The game account slot to set the lock status for.
            member_id (int | str): The ID of the member.
            lock (bool): The lock status to set.

        Returns:
            None: This function does not return anything.
        """
        member = await self.check_member_exists(member_id, get_if_exist=True)
        slot = await self.validate_slot(slot=slot, member=member)
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {f'game_accounts.{slot.name}.lock': lock}}
        )
    
    async def set_image(self, member_id: int | str, image: str | None) -> None:
        """
        Asynchronously sets the image of a member in the database.

        Args:
            member_id (int | str): The ID of the member.
            image (str | None): Base64 encoded image. If None, the image field will be set to None.

        Returns:
            None: This function does not return anything.

        This function updates the 'image' field of the member with the given ID in the database. If the image is None, it sets the image field to None.
        """
        if not isinstance(image, (str, NoneType)):
            raise TypeError(f'image must be either a string or None, not {image.__class__.__name__}')
        
        if isinstance(image, str):
            if len(image) == 0:
                image = None
        
        member = await self.check_member_exists(member_id, get_if_exist=True)
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {'image': image}}
        )
        
    async def set_stats_view_settings(self, slot: AccountSlotsEnum | None, member_id: int | str, settings: StatsViewSettings) -> None:
        """
        Asynchronously sets the stats view settings of a member's game account slot in the database.

        Args:
            slot (AccountSlotsEnum | None): The game account slot to set the stats view settings for.
            member_id (int | str): The ID of the member.
            settings (StatsViewSettings): The stats view settings to set.

        Returns:
            None: This function does not return anything.
        """
        member = await self.check_member_exists(member_id, get_if_exist=True)
        slot = await self.validate_slot(member=member, slot=slot)
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {f'game_accounts.{slot.name}.stats_view_settings': settings.model_dump()}}
        )
        
    async def set_image_settings(self, slot: AccountSlotsEnum | None, member_id: int | str, settings: ImageSettings) -> None:
        """
        Asynchronously sets the image settings of a member's game account slot in the database.

        Args:
            slot (AccountSlotsEnum | None): The game account slot to set the image settings for.
            member_id (int | str): The ID of the member.
            settings (ImageSettings): The image settings to set.

        Returns:
            None: This function does not return anything.
        """
        member = await self.check_member_exists(member_id, get_if_exist=True)
        slot = await self.validate_slot(member=member, slot=slot)
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {f'game_accounts.{slot.name}.image_settings': settings.model_dump()}}
        )
        
    async def get_member_image(self, member_id: int | str | None, member: DBPlayer | None) -> str | None:
        """
        Asynchronously retrieves the image of a specific member.

        Args:
            member_id (int | str | None): The ID of the member.
            member (DBPlayer | None): The member object.

        Returns:
            str | None: The image of the member if it exists, otherwise None.
        """
        member = await self._multi_args_member_checker(member_id, member)
        return member.image
    
    async def set_session_settings(self, slot: AccountSlotsEnum, member_id: int | str, settings: SessionSettings) -> None:
        member = await self.check_member_exists(member_id, get_if_exist=True)
        slot = await self.validate_slot(member=member, slot=slot)
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {f'game_accounts.{slot.name}.session_settings': settings.model_dump()}}
        )
        
    async def get_session_end_time(self, slot: AccountSlotsEnum, member_id: int | str | None = None, member: DBPlayer | None = None) -> datetime:
        member = await self._multi_args_member_checker(member_id, member)
        slot = await self.validate_slot(member=member, slot=slot)
        game_account = await self.get_game_account(slot, member=member)
        return game_account.session_settings.last_get + timedelta(seconds=_config.session.ttl)
    
    async def set_widget_settings(self, slot: AccountSlotsEnum, member_id: int | str, settings: WidgetSettings) -> None:
        member = await self.check_member_exists(member_id, get_if_exist=True)
        slot = await self.validate_slot(member=member, slot=slot)
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {f'game_accounts.{slot.name}.widget_settings': settings.model_dump()}}
        )
        
    async def set_current_account(self, member_id: int | str, slot: AccountSlotsEnum, validate: bool = True) -> None:
        member = await self.check_member_exists(member_id, get_if_exist=True)
        slot = await self.validate_slot(member=member, slot=slot) if validate else slot
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {'current_game_account': slot.name}}
        )
        
    async def set_verification(self, member_id: int | str, slot: AccountSlotsEnum, verified: bool) -> None:
        member = await self.check_member_exists(member_id, get_if_exist=True)
        slot = await self.validate_slot(member=member, slot=slot)
        await self.collection.update_one(
            {'id': int(member_id)},
            {'$set': {f'game_accounts.{slot.name}.verified': verified}}
        )
        
    async def get_member_exp(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> int:
        member = await self._multi_args_member_checker(member_id, member)
        return member.profile.level_exp
    
    async def set_member_exp(self, member_id: int | str, exp: int) -> None:
        await self.collection.update_one(
            {'id': int(member_id)},
            {'$set': {'profile.level_exp': exp}}
        )
        
    async def set_last_activity(self, member_id: int | str, time: datetime = datetime.now(pytz.utc)) -> None:
        await self.collection.update_one(
            {'id': member_id},
            {'$set': {'profile.last_activity': time}}
        )
    
    async def get_last_activity(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> datetime:
        member = await self._multi_args_member_checker(member_id, member)
        return member.profile.last_activity
        
    async def get_analytics(self, member_id: int | str | None = None, member: DBPlayer | None = None, raw: bool = False) -> list[UsedCommand] | list[dict]:
        member = await self._multi_args_member_checker(member_id, member)
        if len(member.profile.used_commands) == 0:
            return []
        
        if raw:
            return [UsedCommand.model_dump(used_command) for used_command in member.profile.used_commands]
    
        return member.profile.used_commands
        
    async def set_analytics(self, analytics: UsedCommand, member: DBPlayer | None = None, member_id: int | str | None = None) -> None:
        member = await self._multi_args_member_checker(member_id, member)
        used_commands: list[dict] = await self.get_analytics(member=member, raw=True)
        
        if (datetime.now(pytz.utc) - member.profile.last_activity) > timedelta(seconds=10):
            level_exp = exp_add(analytics.name)
        else:
            level_exp = 1
        
        if len(used_commands) >= 10:
            used_commands.pop(0)
            
        used_commands.append(analytics.model_dump())
        last_activity = datetime.now(pytz.utc)
        
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {
                'profile.used_commands': used_commands, 
                'profile.last_activity': last_activity,
                'profile.commands_counter' : member.profile.commands_counter + 1,
                'profile.level_exp' : member.profile.level_exp + level_exp
                }
            }
        )
        
    async def set_badges(self, member_id: int | str, badges: list[str]) -> None:
        member = await self.check_member_exists(member_id, get_if_exist=True)
        validated_badges = [validate_badge(badge) for badge in badges if validate_badge(badge) is not None]
        validated_badges = set(
            [*member.profile.badges, *[badge.name for badge in validated_badges]]
        )
        if len(validated_badges) == 0:
            _log.warn(f'Badges {badges} are not valid')
            return
        
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {'profile.badges': list(validated_badges)}}
        )
        
    async def get_badges(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> list[str]:
        member = await self._multi_args_member_checker(member_id, member)
        return member.profile.badges
    
    async def remove_badges(self, member_id: int | str, badges: list[str]) -> None:
        member = await self.check_member_exists(member_id, get_if_exist=True)
        await self.collection.update_one(
            {'id': member.id},
            {'$pull': {'profile.badges': {'$in': badges}}}
        )
    
    async def check_badges(self, member_id: int | str | None = None, member: DBPlayer | None = None) -> None:
        member = await self._multi_args_member_checker(member_id, member)
        for badge in member.profile.badges:
            badge_validated = validate_badge(badge)
            if badge_validated is None:
                member.profile.badges.remove(badge)
                
        await self.collection.update_one(
            {'id': member.id},
            {'$set': {'profile.badges': member.profile.badges}}
        )
        
    async def remove_badge(self, member_id: int | str, badge: str | BadgesEnum) -> None:
        member = await self.check_member_exists(member_id, get_if_exist=True)
        
        if isinstance(badge, BadgesEnum):
            badge = badge.name
            
        await self.collection.update_one(
            {'id': member.id},
            {'$pull': {'profile.badges': badge}}
        )
        
    async def disable_stats_hook(self, member_id: int | str, slot: AccountSlotsEnum) -> None:
        await self.collection.update_one(
            {'id': member_id},
            {'$set': {f'game_accounts.{slot.name}.hook_stats.active': False}}
        )

    async def setup_stats_hook(
        self, 
        member_id: int | str, 
        slot: AccountSlotsEnum,
        hook: HookStats,
    ) -> None:
        await self.collection.update_one(
            {'id': member_id},
            {'$set': {f'game_accounts.{slot.name}.hook_stats': hook.model_dump()}}
        )

    async def database_update(self):
        cursor = self.collection.find({})
        async for member in cursor:
            try:
                old_member = DBPlayerOld.model_validate(member)
            except Exception:
                continue
            
            new_member = {
                '_id' : member['_id'],
                'id': old_member.id,
                'lang' : old_member.lang,
                'image': old_member.image,
                'use_custom_bg': old_member.image_settings.use_custom_bg,
                'game_accounts': {
                    'slot_1' : {
                        'nickname' : old_member.nickname,
                        'game_id' : old_member.game_id,
                        'region' : old_member.region,
                        'last_stats' : old_member.last_stats,
                        'session_settings' : old_member.session_settings.model_dump(),
                        'image_settings' : old_member.image_settings.model_dump(),
                        'widget_settings' : old_member.widget_settings.model_dump(),
                        'stats_view_settings' : old_member.session_settings.stats_view.model_dump(),
                        'verified' : old_member.verified,
                        'locked' : old_member.locked,
                        'hook_stats' : HookStats(),
                    },
                    'slot_2' : None,
                    'slot_3' : None,
                    'slot_4' : None,
                    'slot_5' : None,
                },
                'profile': Profile.model_validate({}),
                'current_game_account': 'slot_1',
            }
            try:
                data = DBPlayer.model_validate(new_member).model_dump()
            except ValueError:
                new_member['game_accounts']['slot_1']['last_stats'] = None
                data = DBPlayer.model_validate(new_member).model_dump()
            
            await self.collection.replace_one(
                {'id': old_member.id},
                replacement=data
            )
            
            _log.debug(f'DB: Player {old_member.id} updated')
            await sleep(0.01)
