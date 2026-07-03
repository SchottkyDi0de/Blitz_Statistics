from motor.motor_asyncio import AsyncIOMotorClient

from lib.data_classes.tankopedia import Tank
from lib.logger import logger
from lib.settings.settings import EnvConfig
from lib.utils.singleton_factory import singleton

_log = logger.get_logger(__file__, 'TankopediaLogger', 'logs/tankopedia.log')


@singleton
class TankopediaDB:
    def __init__(self) -> None:
        self.client = AsyncIOMotorClient(EnvConfig.MONGODB_URI)
        
        self.db = self.client.get_database('TankopediaDB')
        
        self.collection_ru = self.db.get_collection('tanks_ru')
        self.collection_eu = self.db.get_collection('tanks_eu')
        
    async def get_tank_by_id(self, id: int | str, region: str) -> Tank | None:
        id = int(id)
        
        if region == 'ru':
            data = await self.collection_ru.find_one({'id': id})
        else:
            data = await self.collection_eu.find_one({'id': id})
            
        if data is None:
            _log.warn(f"TankopediaDB: tank with id {id} not found in {region} region")
            return data
        
        return Tank.model_validate(data)
    
    async def set_tank(self, tank: Tank, region: str):
        if region == 'ru':
            if await self.collection_ru.find_one({'id': tank.id}) is None:
                await self.collection_ru.insert_one(tank.model_dump())
            else:
                await self.collection_ru.update_one({'id': tank.id}, {'$set': tank.model_dump()})
        else:
            if await self.collection_eu.find_one({'id': tank.id}) is None:
                await self.collection_eu.insert_one(tank.model_dump())
            else:
                await self.collection_eu.update_one({'id': tank.id}, {'$set': tank.model_dump()})
            
    async def set_tanks(self, tanks: list[Tank], region: str):
        if region == 'ru':
            for tank in tanks:
                if await self.collection_ru.find_one({'id': tank.id}) is None:
                    await self.collection_ru.insert_one(tank.model_dump())
                else:
                    await self.collection_ru.update_one({'id': tank.id}, {'$set': tank.model_dump()})
        else:
            for tank in tanks:
                if await self.collection_eu.find_one({'id': tank.id}) is None:
                    await self.collection_eu.insert_one(tank.model_dump())
                else:
                    await self.collection_eu.update_one({'id': tank.id}, {'$set': tank.model_dump()})

    async def del_tank(self, id: int | str, region: str):
        id = int(id)
        
        if region == 'ru':
            await self.collection_ru.delete_one({'id': id})
        else:
            await self.collection_eu.delete_one({'id': id})
