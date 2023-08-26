from python_easy_json import JSONObject


class Meta(JSONObject):
    count: int = None

class Clan(JSONObject):
    members_count: int = None
    name: str = None
    created_at: int = None
    tag: int = None
    clan_id: int = None
    emblem_set_id: int = None

class Data(JSONObject):
    role: str = None
    clan_id: int = None
    joined_at: int = None
    account_id: int = None
    account_name: str = None
    clan: Clan = None

class ClanStats(JSONObject):
    status: str = None
    meta: Meta = None
    data: Data = None
