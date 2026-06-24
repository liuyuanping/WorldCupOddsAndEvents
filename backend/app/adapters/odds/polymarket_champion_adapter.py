"""Polymarket champion odds adapter — real market data for 2026 World Cup."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple

import httpx

from app.adapters.base import OddsProviderAdapter
from app.models.champion import ChampionOddsIn
from app.cache import cache

logger = logging.getLogger(__name__)

# Market data from Polymarket Gamma API (event 30615) — 44 active teams
# Fetched live on 2026-06-23
POLYMARKET_TEAMS: Dict[str, Dict[str, Any]] = {
    "france":       {"token_id": "108233603819467706476318984012158651931658302669301887462181073562758483842092", "name": "法国", "flag": "🇫🇷", "price": 0.1975},
    "argentina":    {"token_id": "18812649149814341758733697580460697418474693998558159483117100240528657629879", "name": "阿根廷", "flag": "🇦🇷", "price": 0.1435},
    "spain":        {"token_id": "4394372887385518214471608448209527405727552777602031099972143344338178308080", "name": "西班牙", "flag": "🇪🇸", "price": 0.1385},
    "england":      {"token_id": "115556263888245616435851357148058235707004733438163639091106356867234218207169", "name": "英格兰", "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "price": 0.1235},
    "portugal":     {"token_id": "45415751658241142530386585138386640503488308219341470020075667342738719018629", "name": "葡萄牙", "flag": "🇵🇹", "price": 0.0675},
    "germany":      {"token_id": "81739002353269632749850710185641576213562066971072676369728657545679630163887", "name": "德国", "flag": "🇩🇪", "price": 0.0565},
    "netherlands":  {"token_id": "55935183786009449883683540312350046975246300613283087403691731856990327029236", "name": "荷兰", "flag": "🇳🇱", "price": 0.0475},
    "brazil":       {"token_id": "27576533317283401577758999384642760405921738493660383550832555714312627457443", "name": "巴西", "flag": "🇧🇷", "price": 0.0445},
    "usa":          {"token_id": "94603648636330087039501304492699481091005420017442244191603206509188088089447", "name": "美国", "flag": "🇺🇸", "price": 0.0355},
    "norway":       {"token_id": "60447443643099453130956385288904175887233107411078568881602330835010340506057", "name": "挪威", "flag": "🇳🇴", "price": 0.0315},
    "japan":        {"token_id": "19159976531313550247579355752030367100657092033093647047491459813592996250034", "name": "日本", "flag": "🇯🇵", "price": 0.0195},
    "morocco":      {"token_id": "69910730841487615802736046038473620030754616421912831175284551372639933569112", "name": "摩洛哥", "flag": "🇲🇦", "price": 0.0165},
    "colombia":     {"token_id": "98803390175521456712653678280474920637934596234667490983228578374641217211132", "name": "哥伦比亚", "flag": "🇨🇴", "price": 0.0145},
    "mexico":       {"token_id": "22587775301869146748237913050505932485648958481571808324285560650057390882036", "name": "墨西哥", "flag": "🇲🇽", "price": 0.0125},
    "belgium":      {"token_id": "30815807067456631524510535002617106205417832891402132396713720656146245200000", "name": "比利时", "flag": "🇧🇪", "price": 0.0115},
    "switzerland":  {"token_id": "62131913648515148266463816694306031394539656598501514114816028349608560215534", "name": "瑞士", "flag": "🇨🇭", "price": 0.0065},
    "croatia":      {"token_id": "106593539437032467615148553707998472829334050617128244920821917025746481184109", "name": "克罗地亚", "flag": "🇭🇷", "price": 0.0045},
    "canada":       {"token_id": "99303605181956827630838461879484468077121754034387765735989859308848389894408", "name": "加拿大", "flag": "🇨🇦", "price": 0.0035},
    "ivory_coast":  {"token_id": "58374167250364215964582274356498746399676421878376948523944979542572589542202", "name": "科特迪瓦", "flag": "🇨🇮", "price": 0.0035},
    "south_korea":  {"token_id": "80724786407275266937534613008558715581084712230616856739273522348302669402554", "name": "韩国", "flag": "🇰🇷", "price": 0.0025},
    "senegal":      {"token_id": "32169302633723235235251659810064817019484855501133685217130365128535248672349", "name": "塞内加尔", "flag": "🇸🇳", "price": 0.0025},
    "australia":    {"token_id": "43661509251351142169227141691164122649250455115438867334436875294380701133091", "name": "澳大利亚", "flag": "🇦🇺", "price": 0.0025},
    "austria":      {"token_id": "88168215299416146215691671077998911754346458567817860712850392736799004561327", "name": "奥地利", "flag": "🇦🇹", "price": 0.0025},
    "egypt":        {"token_id": "30499731947464516579580181356221397335865912996104577000510883912653418218808", "name": "埃及", "flag": "🇪🇬", "price": 0.0025},
    "sweden":       {"token_id": "41004484905556820430171783088292854654441952667499527125436634397522798168110", "name": "瑞典", "flag": "🇸🇪", "price": 0.0025},
    "ghana":        {"token_id": "43907673646206657865778036957293730446366626078011238443367990170655175896145", "name": "加纳", "flag": "🇬🇭", "price": 0.0015},
    "uruguay":      {"token_id": "97239126062673310243763617236644392945530356142765650402171508075574679292913", "name": "乌拉圭", "flag": "🇺🇾", "price": 0.0015},
    "paraguay":     {"token_id": "93165696161088512376930999170413968261015485018106746563527821398897374023845", "name": "巴拉圭", "flag": "🇵🇾", "price": 0.0015},
    "scotland":     {"token_id": "105252206997885252352889070218074909957179496257006510170583432513037465278006", "name": "苏格兰", "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "price": 0.0015},
    "ecuador":      {"token_id": "39971087496427056640429359043364261029374524049464674733142166279730655826181", "name": "厄瓜多尔", "flag": "🇪🇨", "price": 0.0015},
    "congo_dr":     {"token_id": "87403333427856945144645806003352057704193778078820484282942507058200689996202", "name": "民主刚果", "flag": "🇨🇩", "price": 0.0015},
    "new_zealand":  {"token_id": "79609298644734030886284029462369514848707878622071495577618126141372199748974", "name": "新西兰", "flag": "🇳🇿", "price": 0.0005},
    "curacao":      {"token_id": "69020832226510184384177497367584971770730339593583713190288186699694495509961", "name": "库拉索", "flag": "🇨🇼", "price": 0.0005},
    "iran":         {"token_id": "33747305042007778221968790541070114008811587676172030120559423448386310500957", "name": "伊朗", "flag": "🇮🇷", "price": 0.0005},
    "algeria":      {"token_id": "58392024727359233794992635293106675983094683080284912908526627785964160484939", "name": "阿尔及利亚", "flag": "🇩🇿", "price": 0.0005},
    "bosnia":       {"token_id": "89770121993255619705119104591644526712193505786928967250693522950895615785005", "name": "波黑", "flag": "🇧🇦", "price": 0.0005},
    "uzbekistan":   {"token_id": "90538013438399246674125939147272424357773921253199632436930218305581040235987", "name": "乌兹别克斯坦", "flag": "🇺🇿", "price": 0.0005},
    "panama":       {"token_id": "112181485529919660901332188537214992263355343785744498550605179448744432717486", "name": "巴拿马", "flag": "🇵🇦", "price": 0.0005},
    "iraq":         {"token_id": "53465512181802150755993130711224070738002100921790051090044528012833736167995", "name": "伊拉克", "flag": "🇮🇶", "price": 0.0005},
    "south_africa": {"token_id": "29544965695734183971376022965555206180154533479443150154863135205600734339980", "name": "南非", "flag": "🇿🇦", "price": 0.0005},
    "cape_verde":   {"token_id": "61595193871140044336898809781418183952441527621084596848414908595268863899573", "name": "佛得角", "flag": "🇨🇻", "price": 0.0005},
    "czechia":      {"token_id": "35797818400757287472708740881657961304270157125643131597907636474183210188025", "name": "捷克", "flag": "🇨🇿", "price": 0.0005},
    "qatar":        {"token_id": "18605216520960122093689427575806651607517827372535894526532079999408408169156", "name": "卡塔尔", "flag": "🇶🇦", "price": 0.0005},
    "saudi_arabia": {"token_id": "23542782083949026234898323432000742558288032327930681121040136746492993951914", "name": "沙特", "flag": "🇸🇦", "price": 0.0005},
}

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


class PolymarketChampionAdapter(OddsProviderAdapter):
    """Real Polymarket data adapter for World Cup 2026 champion odds."""

    def __init__(self):
        self.config: dict = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._price_cache: Dict[str, List[Tuple[datetime, float]]] = {}

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Polymarket",
            "version": "1.0.0",
            "supported_markets": ["outright"],
            "supported_bookmakers": ["Polymarket"],
            "num_teams": len(POLYMARKET_TEAMS),
            "data_source": "Polymarket CLOB + Gamma API",
        }

    async def initialize(self):
        self._client = httpx.AsyncClient(timeout=30.0)

    async def shutdown(self, grace_period: float = 10.0):
        if self._client:
            await self._client.aclose()

    async def health_check(self) -> bool:
        try:
            if not self._client:
                return False
            resp = await self._client.get(f"{GAMMA_API}/events/30615")
            return resp.status_code == 200
        except Exception:
            return False

    async def fetch_odds(
        self,
        match_id: Optional[str] = None,
        league: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bookmakers: Optional[List[str]] = None,
        markets: Optional[List[str]] = None,
    ) -> List[ChampionOddsIn]:
        """Fetch latest Polymarket prices for all teams."""
        records = []

        # Try to fetch live from Gamma API
        live_prices = {}
        try:
            live_prices = await self._fetch_live_prices()
        except Exception as e:
            logger.warning(f"Could not fetch live Polymarket prices: {e}")

        now = datetime.now(timezone.utc)

        for team_id, info in POLYMARKET_TEAMS.items():
            if match_id and team_id != match_id:
                continue

            price = live_prices.get(team_id, info["price"])
            if price <= 0:
                continue

            records.append(ChampionOddsIn(
                provider="polymarket",
                source_id=f"pm_{team_id}_{now.strftime('%Y%m%d')}",
                team_id=team_id,
                team_name=info["name"],
                bookmaker="Polymarket",
                odds_value=round(1.0 / price, 2) if price > 0 else 999.0,
                implied_probability=round(price, 4),
                timestamp=now,
                received_at=now,
                metadata={
                    "flag": info["flag"],
                    "group": info.get("group", "TBD"),
                    "token_id": info["token_id"],
                    "price_usd": price,
                    "source": "polymarket",
                },
            ))

        return records

    async def stream_odds(self, match_ids, on_update=None):
        records = await self.fetch_odds()
        for r in records:
            if r.team_id in match_ids:
                yield r

    def get_supported_markets(self) -> List[str]:
        return ["outright"]

    def get_supported_bookmakers(self) -> List[str]:
        return ["Polymarket"]

    async def get_teams(self, online: bool = False) -> List[Dict]:
        """Get team list with Polymarket prices. Uses cache unless online=True."""
        cache_key = "champion_teams"

        # Online mode: always fetch fresh
        if not online:
            cached = await cache.get("polymarket", cache_key)
            if cached:
                return cached

        live_prices = {}
        try:
            live_prices = await self._fetch_live_prices()
        except Exception:
            pass

        teams = []
        for team_id, info in POLYMARKET_TEAMS.items():
            price = live_prices.get(team_id, info["price"])
            if price <= 0:
                continue

            teams.append({
                "team_id": team_id,
                "team_name": info["name"],
                "flag_emoji": info["flag"],
                "group": info.get("group", "TBD"),
                "elo_rating": 2000,  # Not available from Polymarket
                "best_odds": round(1.0 / price, 2) if price > 0 else 999,
                "avg_odds": round(1.0 / price, 2) if price > 0 else 999,
                "implied_probability": round(price, 4),
                "odds_trend_30d": 0.0,  # Will be filled by price history
                "recent_form": "→ Stable",
            })

        teams.sort(key=lambda t: t["implied_probability"], reverse=True)
        await cache.set("polymarket", cache_key, teams)
        return teams

    async def get_price_history(
        self, team_id: str, interval: str = "1w", fidelity: int = 30
    ) -> List[Dict]:
        """
        Fetch price history for a team from Polymarket CLOB API.

        Uses startTs to get data beyond the default 30-day window for longer intervals.
        Market created ~2025-07-02.

        Args:
            team_id: Team identifier (e.g., "argentina")
            interval: Time interval (1d, 1w, 1m, all)
            fidelity: Data fidelity (higher = less data)
        """
        info = POLYMARKET_TEAMS.get(team_id)
        if not info or not info["token_id"]:
            return []

        token_id = info["token_id"]
        cache_key = f"{token_id}:{interval}"

        if cache_key in self._price_cache:
            return [
                {"timestamp": ts.isoformat(), "price": p}
                for ts, p in self._price_cache[cache_key]
            ]

        try:
            url = f"{CLOB_API}/prices-history"
            params: dict = {
                "market": token_id,
                "fidelity": str(fidelity),
            }

            now_dt = datetime.now(timezone.utc)
            now_ts = int(now_dt.timestamp())

            # Short intervals (<1 month) use the interval param (CLOB default ~30d)
            # Long intervals use startTs to go back to market creation
            MARKET_CREATED_TS = 1751328000  # ~2025-07-01

            if interval in ("1h", "6h"):
                # Short intervals: use interval param for max CLOB resolution
                params["interval"] = interval
            elif interval in ("1d",):
                params["interval"] = interval
            elif interval in ("1w", "1m"):
                # Use startTs for more control
                params["startTs"] = str(now_ts - self._interval_seconds(interval))
            elif interval in ("all", "max"):
                params["startTs"] = str(MARKET_CREATED_TS)

            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            history = data.get("history", [])
            result = []
            for point in history:
                ts = datetime.fromtimestamp(point["t"], tz=timezone.utc)
                price = float(point["p"])
                result.append((ts, price))

            self._price_cache[cache_key] = result

            return [
                {"timestamp": ts.isoformat(), "price": p}
                for ts, p in result
            ]
        except Exception as e:
            logger.error(f"Failed to fetch price history for {team_id}: {e}")
            return []

    def _interval_seconds(self, interval: str) -> int:
        SECONDS = {"1h": 3600, "6h": 21600, "1d": 86400, "1w": 604800, "1m": 2592000}
        return SECONDS.get(interval, 604800)

    async def _fetch_live_prices(self) -> Dict[str, float]:
        """Fetch current prices from Polymarket Gamma API."""
        if not self._client:
            return {}

        try:
            resp = await self._client.get(f"{GAMMA_API}/events/30615")
            resp.raise_for_status()
            data = resp.json()

            markets = data.get("markets", [])
            prices = {}

            for m in markets:
                question = m.get("question", "")
                outcomes = m.get("outcomePrices", [])
                clob_ids = m.get("clobTokenIds", [])

                if not outcomes or len(outcomes) < 2:
                    continue
                if not clob_ids or len(clob_ids) < 2:
                    continue

                yes_price = float(outcomes[0])
                yes_token = clob_ids[0]

                # Match to our team list
                for team_id, info in POLYMARKET_TEAMS.items():
                    if info["token_id"] == yes_token:
                        prices[team_id] = yes_price
                        break

            return prices
        except Exception as e:
            logger.warning(f"Failed to fetch live prices: {e}")
            return {}
