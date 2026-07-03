from discord import ApplicationContext
from motor.motor_asyncio import AsyncIOMotorClient

from lib.data_classes.db_server import DBServer, ServerSettings
from lib.settings.settings import EnvConfig
from lib.utils.singleton_factory import singleton


@singleton
class ServersDB():
    def __init__(self) -> None:
        self.client = AsyncIOMotorClient(EnvConfig.MONGODB_URI)
        self.db = self.client.get_database('ServersDB')
        self.collection = self.db.get_collection('servers')

    async def set_new_server(self, server_id: int, server_name: str) -> None:
        server_id = str(server_id).strip()
        if await self.collection.find_one() is None:
            await self.collection.insert_one({
                'id': int(server_id),
                'name': server_name,
                'settings': ServerSettings().model_dump(),
                'premium': False,
                'custom_background': None,
                'allow_user_backgrounds': True,
                'work_channels': []
            }
        )
        
    async def del_server_image(self, server_id: int) -> None:
        server_id = str(server_id)
        if self.check_server(server_id):
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'custom_background': None}}
            )
            
    async def check_allow_backgrounds(self, server_id: int) -> bool:
        server_id = str(server_id)
        server = await self.collection.find_one({'id': int(server_id)})
        if server and 'allow_user_backgrounds' in server:
            return server['allow_user_backgrounds']
        else:
            return True
        
    async def check_server(self, server_id: int) -> bool:
        server_id = str(server_id)
        return await self.collection.find_one({'id': int(server_id)}) is not None
        
    async def get_server_image(self, server_id: int) -> str | None:
        server_id = str(server_id)
        server = await self.collection.find_one({'id': int(server_id)})
        if server and 'custom_background' in server:
            return server['custom_background']
        else:
            return None
        
    async def del_server(self, server_id: int) -> None:
        server_id = str(server_id)
        if self.check_server(server_id):
            await self.collection.delete_one({'id': int(server_id)})
        
    async def set_server_image(self, base64_image: str, ctx: ApplicationContext):
        server_id = str(ctx.guild.id)
        if self.check_server(server_id):
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'custom_background': base64_image}}
            )
        else: 
            self.set_new_server(ctx.guild.id, ctx.guild.name)
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'custom_background': base64_image}}
            )
        
    async def set_server_premium(self, server_id: int) -> None:
        if self.check_server(server_id):
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'premium': True}}
            )

    async def unset_server_premium(self, server_id: int) -> None:
        if self.check_server(server_id):
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'premium': False}}
            )

    async def check_server_premium(self, server_id: int) -> bool:
        server_id = str(server_id)
        server = await self.collection.find_one({'id': int(server_id)})
        if server and 'premium' in server:
            return server['premium']
        else:
            return False
        
    async def set_server_settings(self, ctx: ApplicationContext, settings: ServerSettings) -> None:
        server_id = str(ctx.guild.id)
        if self.check_server(server_id):
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'settings': settings.model_dump()}}
            )
        else:
            self.set_new_server(server_id, ctx.guild.name)
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'settings': settings.model_dump()}}
            )
            
    async def get_server_settings(self, ctx: ApplicationContext) -> ServerSettings:
        server_id = str(ctx.guild.id)
        if self.check_server(server_id):
            data = await self.collection.find_one({'id': int(server_id)})
            if data['settings'] is not None:
                return ServerSettings.model_validate(data)
            else:
                self.set_server_settings(ctx, ServerSettings.model_validate({}))
                return ServerSettings.model_validate({})
        else:
            self.set_new_server(server_id, ctx.guild.name)
            self.set_server_settings(ctx, ServerSettings.model_validate({}))
            return ServerSettings.model_validate({})
        
    async def get_server(self, ctx: ApplicationContext) -> DBServer | None:
        res = await self.collection.find_one({'id': ctx.guild.id})
        if res is not None:
            return DBServer.model_validate(res)
        else:
            return None
        
    async def set_work_channels(self, server_id: int, channels: list[int]) -> None:
        server_id = int(server_id)
        if self.check_server(server_id):
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'work_channels': channels}}
            )
        else:
            await self.set_new_server(server_id, 'without_name')
            await self.collection.update_one(
                {'id': int(server_id)},
                {'$set': {'work_channels': channels}}
            )
            
    async def check_work_channels(self, server_id: int, channel: int) -> bool:
        server_id = int(server_id)
        if await self.check_server(server_id):
            server = await self.get_server(server_id)
            if len(server.work_channels) > 0:
                if channel in server.work_channels:
                    return True
                else:
                    return False
            return True
        else:
            True
