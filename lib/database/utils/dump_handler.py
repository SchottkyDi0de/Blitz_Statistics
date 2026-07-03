from os import system
from os.path import exists
from shutil import make_archive

from pymongo import MongoClient

from lib.logger.logger import get_logger
from lib.settings.settings import EnvConfig

_log = get_logger(__file__, 'DumpHandlerLogger', 'logs/dump_handler.log')


class BackUp:
    def __init__(self):
        self.client = MongoClient(EnvConfig.MONGODB_URI)

    def _export_to_google_drive(self):
        ...
    
    def dump(self):
        system("lib/database/utils/bin/mongodump.exe")

        if not exists("dump"):
            _log.error('Failed to create dump')
            return
        
        make_archive('lib/database/utils/dump', 'zip', "dump")

        if not exists("lib/database/utils/dump.zip"):
            _log.error('Failed to create zip')
            return
        
        _log.info('Dump created')
        _log.info('Exporting to Google Drive')
        self._export_to_google_drive()
        
    