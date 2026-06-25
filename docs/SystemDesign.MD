# 赔率-事件关联分析系统 —— 详细系统设计方案


## 一、设计目标

构建一个**可扩展的、多数据源的赔率-事件关联分析平台**，核心能力包括：

1. **多数据源可插拔** —— 赔率数据和事件数据均支持用户自由选择数据源
2. **时间窗口分析** —— 用户选择任意时间区间，系统展示该区间内所有曲线及其关联事件
3. **多曲线-多事件关联** —— 每条曲线可关联多个事件，每个事件可关联到曲线的具体时间点
4. **交互式探索** —— 用户可自由筛选、展示/隐藏事件，钻取查看详情


## 二、总体架构

采用**六层架构**设计，自下而上：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           用户交互层 (Presentation)                         │
│         React/Vue 前端  │  Jupyter Notebook  │  REST API / GraphQL         │
├─────────────────────────────────────────────────────────────────────────────┤
│                        分析引擎层 (Analytics Engine)                        │
│   事件-赔率关联引擎  │  变点检测  │  相关性计算  │  蒙特卡洛模拟  │  预警    │
├─────────────────────────────────────────────────────────────────────────────┤
│                      数据服务层 (Data Service Layer)                        │
│       统一查询接口  │  数据规范化  │  缓存管理  │  数据版本控制              │
├─────────────────────────────────────────────────────────────────────────────┤
│                   数据源适配层 (Data Source Adapter Layer)                  │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│   │ 赔率适配器1  │  │ 赔率适配器2  │  │ 事件适配器1  │  │ 事件适配器2  │      │
│   │ (Odds-API)  │  │(Sportmonks) │  │ (新闻API)   │  │ (GDELT)    │      │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │
├─────────────────────────────────────────────────────────────────────────────┤
│                       数据管道层 (Data Pipeline Layer)                      │
│    实时采集  │  流处理(Kafka/Spark)  │  批量ETL  │  数据质量检查            │
├─────────────────────────────────────────────────────────────────────────────┤
│                       存储层 (Storage Layer)                                │
│   时序数据库  │  关系数据库  │  对象存储  │  缓存(Redis)                   │
└─────────────────────────────────────────────────────────────────────────────┘
```


## 三、数据源适配层（核心设计）

### 3.1 设计原则

- **适配器模式**：每个数据源封装为独立适配器，实现统一接口
- **运行时注册**：数据源可在系统运行时动态注册/注销
- **配置驱动**：每个数据源的连接参数、认证方式、拉取频率均可配置

### 3.2 赔率数据源适配器

| 数据源 | 类型 | 覆盖范围 | 接入方式 | 免费层级 |
|---|---|---|---|---|
| **The Odds API** | REST API | 250+ 博彩公司，主流联赛 | HTTP + SDK (Python/Rust) | 5,000 请求/小时 |
| **Sportmonks API v3** | REST API | 全面足球数据，赛前+滚球赔率 | HTTP | 有限免费 |
| **sportiq-mcp** | MCP Server | 2026世界杯实时赔率 | MCP协议 | 开源 |
| **Football-Data.co.uk** | CSV/静态文件 | 20+欧洲联赛历史赔率 | 直接下载 | 完全免费 |
| **Unified Odds Feed (Sportradar)** | AMQP + XML | 全球赛事，机构级 | SDK (Java/.NET) | 商业授权 |
| **sports-skills** | Python SDK | 多数据源聚合 | pip安装 | 开源 |

**适配器接口定义：**

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

class OddsProviderAdapter(ABC):
    """赔率数据源适配器抽象接口"""
    
    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """返回数据源元信息：名称、支持的市场、延迟等"""
        pass
    
    @abstractmethod
    async def fetch_odds(
        self,
        match_id: Optional[str] = None,
        league: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bookmakers: Optional[List[str]] = None,
        markets: Optional[List[str]] = None
    ) -> List[OddsRecord]:
        """获取赔率数据，支持按比赛、联赛、时间范围、博彩公司筛选"""
        pass
    
    @abstractmethod
    async def stream_odds(
        self,
        match_ids: List[str],
        on_update: Callable[[OddsRecord], None]
    ) -> AsyncIterator:
        """实时流式订阅指定比赛的赔率变动"""
        pass
    
    @abstractmethod
    def get_supported_markets(self) -> List[str]:
        """返回该数据源支持的赔率市场类型（1X2、AH、OU等）"""
        pass
    
    @abstractmethod
    def get_supported_bookmakers(self) -> List[str]:
        """返回该数据源覆盖的博彩公司列表"""
        pass
```

### 3.3 事件数据源适配器

| 数据源 | 类型 | 覆盖范围 | 接入方式 | 特点 |
|---|---|---|---|---|
| **GDELT** | 新闻知识图谱 | 全球新闻，300+事件类别，1979年至今 | REST API / 批量下载 | 每15分钟更新 |
| **sportiq-mcp RAW工具** | MCP Server | 世界杯赛程、阵容、比赛统计 | MCP协议 | 实时赛事事件 |
| **Football-Data.org** | REST API | 欧洲主要联赛赛程、比分 | HTTP | 10请求/分钟免费 |
| **TheSportsDB** | REST API | 球队、球员、赛事历史 | HTTP | 免费公共API |
| **Apify Football Fixtures** | 爬虫/API | 各联赛赛程 | Apify平台 | 免费层可用 |
| **自定义新闻源** | RSS/Webhook | 用户自定义 | 配置接入 | 可扩展 |

**适配器接口定义：**

```python
class EventProviderAdapter(ABC):
    """事件数据源适配器抽象接口"""
    
    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """返回数据源元信息"""
        pass
    
    @abstractmethod
    async def fetch_events(
        self,
        entity_id: Optional[str] = None,      # 球队ID、球员ID等
        event_type: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
        geo_location: Optional[str] = None
    ) -> List[EventRecord]:
        """获取事件数据，支持多维度筛选"""
        pass
    
    @abstractmethod
    async def stream_events(
        self,
        filters: Dict[str, Any],
        on_event: Callable[[EventRecord], None]
    ) -> AsyncIterator:
        """实时事件流订阅"""
        pass
    
    @abstractmethod
    def get_event_categories(self) -> List[str]:
        """返回该数据源支持的事件分类"""
        pass
```

### 3.4 数据源管理

系统提供**数据源注册中心**，用户可通过UI或配置文件管理：

```yaml
# data_sources.yaml
odds_providers:
  - id: the_odds_api
    name: "The Odds API"
    enabled: true
    config:
      api_key: "${ODDS_API_KEY}"
      base_url: "https://api.the-odds-api.com/v4"
      rate_limit: 5000  # requests/hour
    priority: 1  # 数据源优先级，用于冲突解决
    markets: ["h2h", "spreads", "totals"]
    
  - id: sportmonks
    name: "Sportmonks"
    enabled: true
    config:
      api_key: "${SPORTMONKS_KEY}"
      base_url: "https://api.sportmonks.com/v3"
    priority: 2
    
  - id: football_data_co_uk
    name: "Football-Data.co.uk"
    enabled: false  # 用户可手动启用
    config:
      data_path: "/data/football-data"
    priority: 3

event_providers:
  - id: gdelt
    name: "GDELT News Archive"
    enabled: true
    config:
      api_key: "${GDELT_KEY}"
    categories: ["injury", "transfer", "manager_change", "match_result"]
    
  - id: sportiq_raw
    name: "SportIQ Live Events"
    enabled: true
    config:
      # 无额外配置
    categories: ["goal", "card", "substitution", "injury"]
```

### 3.5 插件生命周期与动态注册

```
适配器生命周期状态机:

  ┌──────────┐     register()     ┌──────────┐
  │  CREATED │───────────────────▶│REGISTERED│
  └──────────┘                    └────┬─────┘
                                       │
                              enable() │        disable()
                                       ▼           │
                                  ┌─────────┐      │
                                  │ENABLING │      │
                                  └────┬────┘      │
                                       │           │
                          ┌────────────┼───────┐   │
                          ▼            ▼       ▼   │
                     ┌────────┐  ┌──────────┐ ┌───────┐
                     │ ACTIVE │  │DEGRADED  │ │ERROR  │
                     └───┬────┘  └────┬─────┘ └───┬───┘
                         │            │           │
                         └────────────┼───────────┘
                                      │
                              disable()│   unregister()
                                      ▼        │
                                  ┌──────────┐ │
                                  │DISABLING │◀┘
                                  └────┬─────┘
                                       │
                                       ▼
                                  ┌──────────┐
                                  │ DISABLED │
                                  └──────────┘
```

**插件注册中心实现：**

```python
import importlib
import pkgutil
from typing import Type, Dict, Optional
import inspect
import asyncio

class DataSourceRegistry:
    """
    数据源注册中心
    
    功能:
    - 运行时动态注册/注销数据源适配器
    - 自动发现已安装的适配器包
    - 健康检查与生命周期管理
    """
    
    def __init__(self):
        self._odds_adapters: Dict[str, Type[OddsProviderAdapter]] = {}
        self._event_adapters: Dict[str, Type[EventProviderAdapter]] = {}
        self._instances: Dict[str, Any] = {}
        self._states: Dict[str, AdapterState] = {}
        self._health_tasks: Dict[str, asyncio.Task] = {}
    
    def register(
        self, 
        adapter_class: Type, 
        provider_id: Optional[str] = None
    ) -> str:
        """注册适配器类"""
        provider_id = provider_id or adapter_class.__name__
        
        if issubclass(adapter_class, OddsProviderAdapter):
            self._odds_adapters[provider_id] = adapter_class
        elif issubclass(adapter_class, EventProviderAdapter):
            self._event_adapters[provider_id] = adapter_class
        else:
            raise ValueError(f"Unknown adapter type: {adapter_class}")
        
        self._states[provider_id] = AdapterState.REGISTERED
        logger.info(f"Registered adapter: {provider_id}")
        return provider_id
    
    def auto_discover(self, package_path: str = "adapters"):
        """自动发现已安装的适配器包"""
        package = importlib.import_module(package_path)
        
        for _, module_name, _ in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{package_path}.{module_name}")
            
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, (OddsProviderAdapter, EventProviderAdapter)) \
                   and obj not in (OddsProviderAdapter, EventProviderAdapter):
                    self.register(obj)
    
    async def enable(self, provider_id: str, config: dict) -> bool:
        """启用适配器实例"""
        if provider_id not in self._states:
            raise ValueError(f"Unknown provider: {provider_id}")
        
        self._states[provider_id] = AdapterState.ENABLING
        
        try:
            adapter_class = (
                self._odds_adapters.get(provider_id) or 
                self._event_adapters.get(provider_id)
            )
            
            # 实例化
            instance = adapter_class(config=config)
            await instance.initialize()
            
            self._instances[provider_id] = instance
            self._states[provider_id] = AdapterState.ACTIVE
            
            # 启动健康检查
            self._health_tasks[provider_id] = asyncio.create_task(
                self._health_loop(provider_id, instance)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable {provider_id}: {e}")
            self._states[provider_id] = AdapterState.ERROR
            return False
    
    async def disable(self, provider_id: str, grace_period: float = 10.0):
        """禁用适配器"""
        self._states[provider_id] = AdapterState.DISABLING
        
        # 取消健康检查
        if provider_id in self._health_tasks:
            self._health_tasks[provider_id].cancel()
        
        # 优雅关闭
        instance = self._instances.get(provider_id)
        if instance and hasattr(instance, 'shutdown'):
            await instance.shutdown(grace_period)
        
        self._states[provider_id] = AdapterState.DISABLED
    
    async def _health_loop(self, provider_id: str, instance, interval: int = 30):
        """健康检查循环"""
        while True:
            try:
                await asyncio.sleep(interval)
                healthy = await instance.health_check()
                
                if healthy:
                    if self._states[provider_id] in (AdapterState.DEGRADED,):
                        self._states[provider_id] = AdapterState.ACTIVE
                        logger.info(f"{provider_id} recovered to ACTIVE")
                else:
                    if self._states[provider_id] == AdapterState.ACTIVE:
                        self._states[provider_id] = AdapterState.DEGRADED
                        logger.warning(f"{provider_id} degraded")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check failed for {provider_id}: {e}")
    
    def get_active_odds_providers(self) -> List[str]:
        """获取所有活跃的赔率数据源"""
        return [
            pid for pid, state in self._states.items()
            if pid in self._odds_adaptors and state == AdapterState.ACTIVE
        ]
    
    def get_instance(self, provider_id: str) -> Optional[Any]:
        """获取适配器实例"""
        return self._instances.get(provider_id)
```

### 3.6 自定义数据源SDK

**第三方开发者接入SDK：**

```python
# adapters/custom_odds_adapter.py
"""
自定义赔率数据源开发指南

只需继承 OddsProviderAdapter 并实现5个抽象方法，
然后在配置文件中注册即可。
"""

from odds_correlation_sdk import OddsProviderAdapter, OddsRecord, register_adapter

@register_adapter(
    provider_id="my_custom_odds",
    name="My Custom Odds Provider",
    version="1.0.0"
)
class MyCustomOddsAdapter(OddsProviderAdapter):
    """自定义赔率数据源适配器"""
    
    def get_provider_info(self) -> dict:
        return {
            "name": "My Custom Odds Provider",
            "version": "1.0.0",
            "supported_markets": ["h2h", "over_under"],
            "supported_bookmakers": ["CustomBookmaker"],
            "update_frequency": "real_time",
            "latency_ms": 500,
            "rate_limit": "1000 req/hour",
            "documentation_url": "https://docs.example.com"
        }
    
    async def initialize(self):
        """初始化连接 (注册时调用一次)"""
        self._http_client = aiohttp.ClientSession(
            base_url=self.config["base_url"],
            headers={"Authorization": f"Bearer {self.config['api_key']}"}
        )
        self._ws_client = None
    
    async def fetch_odds(self, **filters) -> List[OddsRecord]:
        """从自定义API拉取赔率数据"""
        params = self._build_query_params(filters)
        
        async with self._http_client.get("/api/v1/odds", params=params) as resp:
            if resp.status == 429:
                raise RateLimitError("Rate limit exceeded")
            
            data = await resp.json()
            
            # 映射到标准 OddsRecord 格式
            return [
                OddsRecord(
                    provider="my_custom_odds",
                    source_id=f"custom_{item['id']}",
                    match_id=item["fixture_id"],
                    bookmaker="CustomBookmaker",
                    market=self._map_market(item["market"]),
                    selection=item["outcome"],
                    odds_value=float(item["price"]),
                    odds_format=OddsFormat.DECIMAL,
                    implied_probability=1.0 / float(item["price"]),
                    timestamp=datetime.fromisoformat(item["updated_at"]),
                    received_at=datetime.utcnow(),
                    metadata={"raw": item}
                )
                for item in data["odds"]
            ]
    
    async def stream_odds(self, match_ids: List[str], 
                          on_update: Callable) -> AsyncIterator:
        """WebSocket实时流订阅"""
        self._ws_client = await self._http_client.ws_connect("/ws/odds/live")
        
        # 订阅指定比赛
        await self._ws_client.send_json({
            "action": "subscribe",
            "match_ids": match_ids
        })
        
        async for msg in self._ws_client:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                record = self._parse_ws_message(data)
                if record:
                    yield record
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            async with self._http_client.get("/health") as resp:
                return resp.status == 200
        except Exception:
            return False
    
    async def shutdown(self, grace_period: float = 10.0):
        """优雅关闭"""
        if self._ws_client:
            await self._ws_client.close()
        if self._http_client:
            await self._http_client.close()
    
    def get_supported_markets(self) -> List[str]:
        return ["h2h", "over_under", "asian_handicap"]
    
    def get_supported_bookmakers(self) -> List[str]:
        return ["CustomBookmaker"]
    
    def _map_market(self, market: str) -> str:
        """将自定义市场代码映射到标准类型"""
        MAPPING = {
            "1X2": "h2h",
            "OU": "over_under",
            "AH": "asian_handicap"
        }
        return MAPPING.get(market, market.lower())
```
```


## 四、核心数据模型

### 4.1 赔率数据模型

```python
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

class OddsFormat(Enum):
    DECIMAL = "decimal"
    AMERICAN = "american"
    HONGKONG = "hongkong"
    INDONESIAN = "indonesian"
    MALAY = "malay"

class OddsRecord:
    """单条赔率记录"""
    id: str
    provider: str                    # 数据源标识
    match_id: str                    # 比赛唯一标识
    bookmaker: str                   # 博彩公司名称
    market: str                      # 市场类型: h2h, over_under, asian_handicap
    selection: str                   # 选项: home, away, draw, over, under
    odds_value: float                # 赔率值（统一转为Decimal）
    odds_format: OddsFormat          # 原始格式
    implied_probability: float       # 隐含概率
    timestamp: datetime              # 赔率生效时间
    received_at: datetime            # 系统收到时间
    volume: Optional[float]          # 交易量（如有）
    metadata: Dict[str, any]         # 扩展字段
```

### 4.2 事件数据模型

```python
class EventSeverity(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class EventRecord:
    """单条事件记录"""
    id: str
    provider: str                    # 数据源标识
    event_type: str                  # 事件类型: injury, transfer, goal, red_card
    title: str                       # 事件标题
    description: str                 # 事件描述
    timestamp: datetime              # 事件发生时间
    detected_at: datetime            # 系统检测到时间
    severity: EventSeverity          # 严重程度
    entities: List[Dict]             # 关联实体: [{type: "team", id: "xxx", name: "..."}]
    source_url: Optional[str]        # 来源链接
    confidence: float                # 置信度 (0-1)
    metadata: Dict[str, any]         # 扩展字段
    # 关联信息（由关联引擎填充）
    related_odds_ids: List[str]      # 关联的赔率记录ID列表
    related_curves: List[str]        # 关联的曲线ID列表
```

### 4.3 曲线定义模型

```python
class CurveDefinition:
    """用户定义的曲线"""
    id: str
    name: str                        # 曲线名称，如 "英格兰胜赔率"
    type: CurveType                  # odds, price, spread, volatility
    source: Dict[str, any]           # 数据源定义
    calculation: Optional[str]       # 衍生指标的计算公式
    # 例如: 
    # source = {
    #   "provider": "the_odds_api",
    #   "match_id": "england_vs_france",
    #   "bookmaker": "Pinnacle",
    #   "market": "h2h",
    #   "selection": "home"
    # }
```

### 4.4 关联记录模型

```python
class EventOddsCorrelation:
    """事件-赔率关联记录"""
    id: str
    event_id: str
    odds_id: str
    curve_id: str                    # 关联到具体曲线
    timestamp: datetime              # 关联时间点（事件时间对齐到赔率时间轴）
    correlation_score: float         # 关联强度评分 (0-1)
    lag_seconds: int                 # 事件发生后赔率变动的延迟（秒）
    magnitude: float                 # 赔率变动幅度
    direction: str                   # up / down / neutral
    detection_method: str            # 检测方法: manual, changepoint, ml
    confidence: float
    metadata: Dict[str, any]
```


## 五、数据管道层

### 5.1 实时流处理架构

参考业界最佳实践，采用 **采集 → 队列 → 规范化 → 持久化** 四阶段架构：

```
┌──────────────┐    ┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  数据源       │───▶│  Kafka      │───▶│  规范化服务   │───▶│  Kafka      │
│  (WebSocket) │    │  (raw)      │    │  (Schema归一) │    │  (normalized)│
└──────────────┘    └─────────────┘    └──────────────┘    └─────────────┘
                                                                   │
                                                                   ▼
┌──────────────┐    ┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  持久化       │◀───│  流处理      │◀───│  Kafka       │    │  实时查询    │
│  (Timescale) │    │  (Spark)    │    │  (normalized)│    │  (Redis)    │
└──────────────┘    └─────────────┘    └──────────────┘    └─────────────┘
```

**关键设计要点：**
- **每个数据源独立采集器**：使用Python asyncio + WebSocket，每个provider一个轻量级进程
- **原始数据直存Kafka**：采集器只负责"拿到数据放入Kafka"，不做任何解析转换
- **规范化服务独立**：Schema统一、去重、格式转换在独立的消费者中完成
- **纳秒级时间戳**：在采集入口打上`received_at`时间戳，用于延迟分析

### 5.2 批处理与历史数据

参考BetFlow的Lambda架构：

- **批量ETL**：使用Apache Airflow调度，每日从CSV/历史API拉取数据
- **数据湖**：原始数据存入S3/OSS（`raw-s3/topics`）
- **OLAP分析**：使用Apache Druid或ClickHouse支持高效的历史数据聚合查询
- **数据质量检查**：自动化检查数据完整性、异常值检测

### 5.3 采集器详细设计

**采集器生命周期状态机：**

```
                    ┌──────────┐
           ┌───────▶│  ACTIVE   │◀──────┐
           │        └─────┬─────┘       │
           │              │             │
    启动成功│         ┌────▼────┐   恢复成功
           │         │ BACKOFF │       │
    ┌──────┴──┐      └────┬────┘  ┌────┴──────┐
    │INIT     │           │       │ DEGRADED   │
    └──────┬──┘     ┌────▼────┐  └────┬──────┘
           │        │  ERROR   │◀──────┘
           └───────▶│          │  连续失败
           启动失败  └────┬────┘
                         │ 不可恢复错误
                    ┌────▼────┐
                    │  DEAD    │
                    └─────────┘
```

**采集器核心实现：**

```python
import asyncio
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class CollectorState(Enum):
    INIT = "init"
    ACTIVE = "active"
    BACKOFF = "backoff"
    DEGRADED = "degraded"
    ERROR = "error"
    DEAD = "dead"

@dataclass
class CollectorConfig:
    """采集器配置"""
    provider_id: str
    poll_interval_ms: int = 500           # 拉取模式间隔
    max_retries: int = 5
    backoff_base_ms: int = 1000           # 退避基础时间
    backoff_max_ms: int = 60000           # 退避上限
    backoff_multiplier: float = 2.0
    max_lag_seconds: int = 300            # 超过此延迟进入 DEGRADED
    health_check_interval_ms: int = 10000

@dataclass
class CollectorMetrics:
    """采集器运行时指标"""
    state: CollectorState = CollectorState.INIT
    messages_collected: int = 0
    messages_errors: int = 0
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    current_lag_ms: float = 0.0           # 当前端到端延迟
    consecutive_errors: int = 0
    uptime_seconds: float = 0.0

class OddsDataCollector:
    """
    单数据源采集器
    
    职责边界：只负责"获取数据 → 放入Kafka"，不做任何解析转换。
    每个 provider 一个独立进程实例，故障隔离。
    """
    
    def __init__(
        self,
        config: CollectorConfig,
        adapter: OddsProviderAdapter,
        kafka_producer: KafkaProducer,
        metrics_registry: MetricsRegistry
    ):
        self.config = config
        self.adapter = adapter
        self.kafka = kafka_producer
        self.metrics = CollectorMetrics()
        self._state = CollectorState.INIT
        self._stop_event = asyncio.Event()
        self._backoff_attempt = 0
    
    async def run(self):
        """采集器主循环"""
        self._transition(CollectorState.ACTIVE)
        self.metrics.uptime_seconds = 0
        start_time = datetime.now()
        
        while not self._stop_event.is_set():
            try:
                # 从数据源拉取数据
                async for batch in self.adapter.stream_odds(
                    match_ids=self._subscribed_matches,
                    on_update=None  # 批量模式
                ):
                    if self._stop_event.is_set():
                        break
                    
                    # 打上纳秒级接收时间戳
                    received_at = datetime.utcnow()
                    for record in batch:
                        record.received_at = received_at
                        record._collector_lag_ms = (
                            received_at - record.timestamp
                        ).total_seconds() * 1000
                    
                    # 直接写入Kafka原始topic，不做任何转换
                    await self._publish_raw_batch(batch)
                    
                    # 更新指标
                    self.metrics.messages_collected += len(batch)
                    self.metrics.last_success_at = received_at
                    self.metrics.consecutive_errors = 0
                    self._backoff_attempt = 0
                    
                    # 如果之前在 DEGRADED/BACKOFF 状态，恢复
                    if self._state in (CollectorState.DEGRADED, CollectorState.BACKOFF):
                        self._transition(CollectorState.ACTIVE)
                
            except asyncio.CancelledError:
                break
                
            except RateLimitError as e:
                # 速率限制 → 指数退避
                self._handle_transient_error(e, "rate_limited")
                
            except (ConnectionError, TimeoutError) as e:
                # 网络错误 → 退避
                self._handle_transient_error(e, "network_error")
                
            except AuthenticationError as e:
                # 认证错误 → 不可恢复，进入DEAD
                self._handle_fatal_error(e, "auth_failed")
                break
                
            except Exception as e:
                self._handle_transient_error(e, "unknown")
            
            # 更新运行时间
            self.metrics.uptime_seconds = (
                datetime.now() - start_time
            ).total_seconds()
    
    async def _publish_raw_batch(self, batch: List[OddsRecord]):
        """发布原始数据到Kafka —— 不做任何转换"""
        topic = f"raw.odds.{self.config.provider_id}"
        messages = [
            {
                "key": f"{r.match_id}:{r.bookmaker}:{r.market}".encode(),
                "value": r.model_dump_json().encode(),
                "headers": {
                    "provider": self.config.provider_id,
                    "received_at": str(r.received_at.isoformat()),
                    "source": "collector"
                }
            }
            for r in batch
        ]
        await self.kafka.send_batch(topic, messages)
    
    def _handle_transient_error(self, error: Exception, error_type: str):
        """处理可恢复错误 —— 指数退避"""
        self.metrics.consecutive_errors += 1
        self.metrics.last_error_at = datetime.now()
        self.metrics.last_error_message = str(error)
        self.metrics.messages_errors += 1
        
        if self.metrics.consecutive_errors >= self.config.max_retries:
            self._transition(CollectorState.DEGRADED)
        else:
            self._transition(CollectorState.BACKOFF)
        
        # 计算退避时间
        delay = min(
            self.config.backoff_base_ms * 
            (self.config.backoff_multiplier ** self._backoff_attempt),
            self.config.backoff_max_ms
        )
        self._backoff_attempt += 1
        
        logger.warning(
            f"[{self.config.provider_id}] {error_type} error, "
            f"backoff={delay}ms, attempt={self._backoff_attempt}: {error}"
        )
        
        # 异步等待退避
        asyncio.ensure_future(self._backoff_sleep(delay / 1000))
    
    async def _backoff_sleep(self, seconds: float):
        await asyncio.sleep(seconds)
    
    def _handle_fatal_error(self, error: Exception, error_type: str):
        """处理不可恢复错误"""
        self.metrics.last_error_at = datetime.now()
        self.metrics.last_error_message = str(error)
        self._transition(CollectorState.DEAD)
        logger.error(
            f"[{self.config.provider_id}] FATAL {error_type}: {error}"
        )
    
    def _transition(self, new_state: CollectorState):
        old_state = self._state
        self._state = new_state
        self.metrics.state = new_state
        logger.info(
            f"[{self.config.provider_id}] State: {old_state.value} → {new_state.value}"
        )
    
    async def shutdown(self, grace_period: float = 10.0):
        """优雅关闭"""
        logger.info(f"[{self.config.provider_id}] Shutting down...")
        self._stop_event.set()
        # 等待进行中的批次完成
        await asyncio.sleep(min(grace_period, 2.0))
```

### 5.4 Schema规范化引擎

```
规范化流程:

  Kafka(raw) ──▶ Consumer Group ──▶ Normalizer ──▶ Kafka(normalized)
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                     Schema映射      格式统一         去重检测
                    (DSL驱动)     (Decimal归一)    (provider+source_id)
                          │               │               │
                          ▼               ▼               ▼
                     ┌─────────────────────────────────────────┐
                     │         EnrichedRecord                   │
                     │  - 原始字段映射到标准化字段              │
                     │  - 赔率格式统一为 Decimal                │
                     │  - 计算 implied_probability              │
                     │  - 标记数据质量分数                      │
                     └─────────────────────────────────────────┘
```

**Schema映射DSL：**

```yaml
# schema_mappings/the_odds_api.yaml
# 声明式定义如何将 The Odds API 的响应映射到标准模型

provider: the_odds_api
version: 1

field_mappings:
  # 直接映射 (source_field → target_field)
  direct:
    match_id: "id"
    bookmaker: "bookmakers[].title"
    
  # 转换映射 (需要类型转换或计算)
  transforms:
    odds_value:
      source: "bookmakers[].markets[].outcomes[].price"
      type: float
    market:
      source: "bookmakers[].markets[].key"
      type: enum
      values:
        h2h: "h2h"
        spreads: "asian_handicap"
        totals: "over_under"
    selection:
      source: "bookmakers[].markets[].outcomes[].name"
      type: string
    implied_probability:
      source: "bookmakers[].markets[].outcomes[].price"
      transform: "1.0 / value"   # Decimal赔率 → 隐含概率
    odds_format:
      value: "decimal"            # 固定值

  # 时间戳处理
  timestamps:
    timestamp:
      source: "bookmakers[].markets[].last_update"
      format: "iso8601"
      timezone: "UTC"
    
  # 质量标记
  quality_checks:
    - rule: "odds_value > 0"
      action: "reject_row"
    - rule: "odds_value > 1.0"
      action: "flag_suspicious"
    - rule: "implied_probability > 0 and implied_probability < 1"
      action: "reject_row"
```

**规范化处理器实现：**

```python
import hashlib
from typing import Dict, Any, Optional
import json

class SchemaNormalizer:
    """
    Schema规范化处理器
    
    消费 raw topic，产出 normalized topic。
    使用声明式DSL进行字段映射，避免硬编码。
    """
    
    def __init__(self, mapping_registry: MappingRegistry):
        self.registry = mapping_registry
    
    async def normalize(self, raw_message: KafkaMessage) -> Optional[EnrichedRecord]:
        provider = raw_message.headers["provider"]
        mapping = self.registry.get(provider)
        
        if not mapping:
            logger.error(f"No mapping found for provider: {provider}")
            return None
        
        raw = json.loads(raw_message.value)
        
        try:
            # Step 1: 应用字段映射
            record = self._apply_mapping(raw, mapping)
            
            # Step 2: 数据质量检查
            quality_score, issues = self._quality_check(record, mapping)
            if not issues.critical:
                record.quality_score = quality_score
            else:
                # 写入死信队列
                await self._send_to_dlq(raw, issues)
                return None
            
            # Step 3: 生成去重键
            record.dedup_key = hashlib.sha256(
                f"{record.provider}:{record.source_id}".encode()
            ).hexdigest()
            
            # Step 4: 附加元数据
            record.normalized_at = datetime.utcnow()
            record.schema_version = mapping.version
            
            return record
            
        except Exception as e:
            logger.error(f"Normalization failed for {provider}: {e}")
            await self._send_to_dlq(raw, MappingError(str(e)))
            return None
    
    def _apply_mapping(self, raw: Dict, mapping: FieldMapping) -> OddsRecord:
        """应用声明式字段映射"""
        record = OddsRecord()
        
        # 直接映射
        for target, source_path in mapping.direct.items():
            value = self._extract_nested(raw, source_path)
            setattr(record, target, value)
        
        # 转换映射
        for target, transform_def in mapping.transforms.items():
            if "value" in transform_def:
                # 固定值
                value = transform_def["value"]
            else:
                value = self._extract_nested(raw, transform_def["source"])
                if transform_def.get("transform"):
                    value = self._eval_transform(value, transform_def["transform"])
            setattr(record, target, value)
        
        return record
    
    def _extract_nested(self, obj: Dict, path: str) -> Any:
        """
        提取嵌套字段，支持数组索引
        例: "bookmakers[].markets[].key" 
        """
        parts = path.replace("[]", "").split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # 取第一个元素（批量展开在外部处理）
                current = current[0].get(part) if current else None
        return current
    
    def _quality_check(self, record: OddsRecord, mapping: FieldMapping) -> Tuple[float, QualityIssues]:
        """执行数据质量检查规则"""
        score = 1.0
        issues = QualityIssues()
        
        for check in mapping.quality_checks:
            result = self._eval_rule(record, check["rule"])
            if not result:
                if check["action"] == "reject_row":
                    issues.critical.append(check["rule"])
                    score = 0.0
                elif check["action"] == "flag_suspicious":
                    issues.warnings.append(check["rule"])
                    score -= 0.1
        
        return max(score, 0.0), issues
```

### 5.5 精确一次语义与去重

```python
class ExactlyOnceProcessor:
    """
    实现 at-least-once 投递 + 幂等写入 → exactly-once 效果
    
    策略:
    1. Kafka producer: enable.idempotence=true, acks=all
    2. 写入层: INSERT ... ON CONFLICT (provider, source_id) DO NOTHING
    3. 去重窗口: Redis Bitmap (最近24小时的去重指纹)
    """
    
    def __init__(self, redis: Redis, db_pool: AsyncConnectionPool):
        self.redis = redis
        self.db = db_pool
    
    async def process_batch(self, records: List[EnrichedRecord]) -> BatchResult:
        """处理一批规范化记录，保证精确一次"""
        
        # Phase 1: 快速去重 (Redis Bloom Filter)
        candidates = []
        for record in records:
            dedup_fingerprint = self._fingerprint(record)
            exists = await self.redis.getbit(
                f"dedup:{datetime.utcnow():%Y%m%d%H}", 
                self._hash_to_offset(dedup_fingerprint)
            )
            if not exists:
                candidates.append(record)
                # 标记为已见 (允许少量误判，数据库层做最终去重)
                await self.redis.setbit(
                    f"dedup:{datetime.utcnow():%Y%m%d%H}",
                    self._hash_to_offset(dedup_fingerprint),
                    1
                )
        
        if not candidates:
            return BatchResult(processed=0, duplicates=len(records), errors=0)
        
        # Phase 2: 数据库幂等写入
        async with self.db.transaction():
            result = await self.db.execute(
                """
                INSERT INTO odds_records (
                    provider, source_id, match_id, bookmaker, market,
                    selection, odds_value, odds_format, implied_prob,
                    timestamp, received_at, metadata
                )
                SELECT 
                    r.provider, r.source_id, r.match_id, r.bookmaker, r.market,
                    r.selection, r.odds_value, r.odds_format, r.implied_prob,
                    r.timestamp, r.received_at, r.metadata
                FROM UNNEST($1::odds_records[]) AS r
                ON CONFLICT (provider, source_id) DO NOTHING
                RETURNING 1
                """,
                candidates
            )
            inserted = len(result)
        
        duplicates = len(candidates) - inserted
        return BatchResult(
            processed=inserted,
            duplicates=len(records) - len(candidates) + duplicates,
            errors=0
        )
    
    def _fingerprint(self, record: EnrichedRecord) -> str:
        """生成去重指纹"""
        return f"{record.provider}:{record.source_id}:{record.timestamp.isoformat()}"
    
    def _hash_to_offset(self, fingerprint: str) -> int:
        """Hash → Bitmap offset (2^20 = 1M bits per hour window)"""
        return int(hashlib.md5(fingerprint.encode()).hexdigest()[:5], 16) % (2 ** 20)
```

### 5.6 反压与流量控制

```
反压传播链:

  DB写入慢 ──▶ Kafka消费者延迟 ──▶ normalized topic积压 ──▶ 
  Normalizer处理慢 ──▶ raw topic积压 ──▶ Collector降低采集频率

实现机制:
  - Kafka Consumer: pause()/resume() 分区
  - Collector: 自适应轮询间隔 (根据Kafka lag动态调整)
  - Normalizer: 动态扩缩 (KEDA based on consumer group lag)
```

```python
class AdaptivePollController:
    """
    自适应采集频率控制
    
    根据端到端管道延迟动态调整采集间隔，实现被动反压。
    """
    
    def __init__(self, base_interval_ms: int = 500):
        self.base_interval = base_interval_ms
        self.current_interval = base_interval_ms
        self.max_interval = 30000
        self.min_interval = 100
    
    async def calculate_next_delay(
        self,
        pipeline_lag_ms: float,
        error_rate: float,
        consecutive_errors: int
    ) -> float:
        """
        综合计算下次采集延迟
        
        输入信号:
        - pipeline_lag_ms: 端到端管道延迟
        - error_rate: 近期错误率
        - consecutive_errors: 连续错误次数
        """
        delay = self.base_interval
        
        # 信号1: 管道积压 → 增大间隔
        if pipeline_lag_ms > 5000:       # >5s lag
            delay *= 4
        elif pipeline_lag_ms > 2000:     # >2s lag
            delay *= 2
        elif pipeline_lag_ms < 200:      # <200ms lag, 健康
            delay = max(delay / 2, self.min_interval)
        
        # 信号2: 错误率 → 退避
        if error_rate > 0.1:             # >10% 错误率
            delay *= 3
        
        # 信号3: 连续错误 → 指数退避
        if consecutive_errors > 0:
            delay *= (2 ** min(consecutive_errors, 5))
        
        return min(delay, self.max_interval)
```

### 5.7 数据质量框架

```python
@dataclass
class DataQualityReport:
    """每小时生成的数据质量报告"""
    provider_id: str
    window_start: datetime
    window_end: datetime
    
    # 完整性指标
    expected_records: int           # 预期数据点数
    actual_records: int             # 实际数据点数
    completeness_pct: float         # 完整率
    gap_count: int                  # 数据缺口数
    max_gap_seconds: float          # 最大缺口时长
    
    # 准确性指标
    outlier_count: int              # 异常值数 (>3σ)
    stale_count: int                # 陈旧数据数 (延迟>阈值)
    invalid_format_count: int       # 格式错误数
    
    # 及时性指标
    p50_lag_ms: float
    p95_lag_ms: float
    p99_lag_ms: float
    
    # 一致性指标
    cross_source_discrepancy_pct: float  # 跨数据源价格分歧 %
    duplicate_rate_pct: float
    
    @property
    def health_score(self) -> float:
        """综合健康评分 0-100"""
        scores = []
        scores.append(self.completeness_pct * 0.35)
        scores.append(max(0, 100 - self.outlier_count * 5) * 0.20)
        scores.append(max(0, 100 - self.p95_lag_ms / 100) * 0.25)
        scores.append(max(0, 100 - self.duplicate_rate_pct * 10) * 0.20)
        return sum(scores)

class DataQualityMonitor:
    """数据质量持续监控"""
    
    async def run_hourly_check(self, provider_id: str) -> DataQualityReport:
        """每小时质量检查"""
        window_end = datetime.utcnow()
        window_start = window_end - timedelta(hours=1)
        
        report = DataQualityReport(
            provider_id=provider_id,
            window_start=window_start,
            window_end=window_end
        )
        
        # 1. 完整性检查: 每个match_id应该有持续的数据点
        report.actual_records = await self._count_records(provider_id, window_start, window_end)
        report.expected_records = await self._estimate_expected(provider_id, window_start, window_end)
        report.completeness_pct = (report.actual_records / max(report.expected_records, 1)) * 100
        
        # 2. 缺口检测: 连续数据点间的时间间隔
        gaps = await self._detect_gaps(provider_id, window_start, window_end)
        report.gap_count = len(gaps)
        report.max_gap_seconds = max(gaps).total_seconds() if gaps else 0
        
        # 3. 异常值检测: 使用修正Z-score (MAD)
        report.outlier_count = await self._count_outliers_mad(provider_id, window_start, window_end)
        
        # 4. 延迟统计
        lag_stats = await self._calculate_lag_percentiles(provider_id, window_start, window_end)
        report.p50_lag_ms = lag_stats.p50
        report.p95_lag_ms = lag_stats.p95
        report.p99_lag_ms = lag_stats.p99
        
        return report
    
    async def _count_outliers_mad(self, provider_id: str, start: datetime, end: datetime) -> int:
        """使用MAD (Median Absolute Deviation) 检测异常值"""
        result = await self.db.execute(
            """
            WITH stats AS (
                SELECT 
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY odds_value) AS median,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(odds_value - 
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY odds_value)
                    )) AS mad
                FROM odds_records
                WHERE provider = $1 AND timestamp BETWEEN $2 AND $3
            )
            SELECT COUNT(*) 
            FROM odds_records, stats
            WHERE provider = $1 
              AND timestamp BETWEEN $2 AND $3
              AND ABS(odds_value - stats.median) / NULLIF(stats.mad, 0) > 3.5
            """,
            provider_id, start, end
        )
        return result.scalar()
```


## 六、分析引擎层

### 6.1 事件-赔率关联引擎

**核心功能**：自动检测事件与赔率变动的对应关系

```python
class EventOddsCorrelationEngine:
    """事件-赔率关联引擎"""
    
    async def detect_correlations(
        self,
        events: List[EventRecord],
        odds_series: Dict[str, List[OddsRecord]],  # curve_id -> odds timeline
        time_window: Tuple[datetime, datetime],
        methods: List[str] = ["changepoint", "event_window", "ml"]
    ) -> List[EventOddsCorrelation]:
        """
        检测事件与赔率曲线的关联
        
        三种检测方法:
        1. changepoint: 在事件时间点前后检测赔率曲线的统计变点
        2. event_window: 在事件发生后的固定时间窗口内检测赔率变动
        3. ml: 使用机器学习模型预测事件对赔率的影响
        """
        pass
    
    async def calculate_correlation_score(
        self,
        event: EventRecord,
        odds_timeline: List[OddsRecord],
        lag_range: Tuple[int, int]  # 搜索延迟范围（秒）
    ) -> CorrelationResult:
        """
        计算单个事件与赔率时间线的关联强度
        使用互相关分析(Cross-Correlation)找到最优延迟
        """
        pass
```

**变点检测方法**：

1. **统计变点检测**：在事件时间点前后使用CUSUM或Pruned Exact Linear Time (PELT)算法检测赔率序列的结构突变
2. **事件窗口分析**：在事件发生后固定窗口（如30秒、1分钟、5分钟）内，计算赔率的最大变动幅度和方向
3. **机器学习方法**：训练模型预测事件对特定赔率的影响方向和幅度

### 6.2 衍生分析模块

| 模块 | 功能 | 技术实现 |
|---|---|---|
| **预期价值计算** | 对比模型概率与市场赔率，识别+EV机会 | sportiq-mcp `football_find_value_bets` |
| **蒙特卡洛模拟** | 模拟赛事结果分布，计算各队出线/夺冠概率 | sportiq-mcp `football_simulate_bracket` |
| **市场效率分析** | 评估事件信息是否已被市场充分定价 | 事件窗口内赔率变动速度与幅度分析 |
| **异常预警** | 检测无事件驱动的异常赔率变动 | 时序异常检测算法 |
| **趋势分析** | 滚动窗口分析赔率趋势与事件累积效应 | sportiq-mcp `football_form_trends` |

### 6.3 CUSUM 变点检测算法

**数学原理：**

CUSUM (Cumulative Sum Control Chart) 通过累积偏差检测序列的结构突变。给定赔率序列 `{x₁, x₂, ..., xₙ}`，计算：

```
S₀ = 0
Sₜ = max(0, Sₜ₋₁ + (xₜ - μ₀ - k))
其中: μ₀ = 目标均值（滑动窗口估计）
      k = 允许偏差（通常设为 0.5δ，δ为期望检测的最小变幅）
触发: 当 Sₜ > h (控制限) 时检测到正向变点
```

**完整实现：**

```python
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class ChangepointResult:
    """变点检测结果"""
    timestamp: datetime
    confidence: float           # 0-1
    magnitude: float            # 变动幅度 (绝对)
    direction: str              # "up" | "down"
    pre_mean: float             # 变点前均值
    post_mean: float            # 变点后均值
    detection_lag_ms: float     # 检测延迟 (从变点发生到检测到)

class CUSUMChangepointDetector:
    """
    双CUSUM变点检测器
    
    同时运行两个CUSUM:
    - S⁺ 检测向上突变（赔率上升）
    - S⁻ 检测向下突变（赔率下降）
    """
    
    def __init__(
        self,
        threshold: float = 5.0,         # h: 控制限
        drift: float = 0.5,             # k: 允许漂移
        estimation_window: int = 60,    # 均值估计窗口（数据点数）
        min_change_magnitude: float = 0.02  # 最小变幅（相对值）
    ):
        self.h = threshold
        self.k = drift
        self.estimation_window = estimation_window
        self.min_change = min_change_magnitude
        
        # 状态
        self.S_pos = 0.0      # 正向CUSUM
        self.S_neg = 0.0      # 负向CUSUM
        self.mu_hat = None    # 估计均值
        self.buffer = []      # 滑动窗口
    
    def update(self, value: float, timestamp: datetime) -> Optional[ChangepointResult]:
        """逐个数据点更新，返回是否检测到变点"""
        self.buffer.append(value)
        
        # 维护滑动窗口
        if len(self.buffer) > self.estimation_window * 3:
            self.buffer = self.buffer[-self.estimation_window:]
        
        # 定期重新估计均值（每 estimation_window 个点）
        if len(self.buffer) >= self.estimation_window and len(self.buffer) % (self.estimation_window // 2) == 0:
            recent = self.buffer[-self.estimation_window:]
            self.mu_hat = np.mean(recent)
        
        if self.mu_hat is None:
            return None
        
        # 标准化偏差
        normalized_deviation = (value - self.mu_hat) / max(abs(self.mu_hat), 0.001)
        
        # 更新CUSUM统计量
        self.S_pos = max(0, self.S_pos + normalized_deviation - self.k)
        self.S_neg = max(0, self.S_neg - normalized_deviation - self.k)
        
        # 检查是否触发
        if self.S_pos > self.h:
            result = self._build_result(value, "up", self.S_pos, timestamp)
            self._reset()
            return result
        
        if self.S_neg > self.h:
            result = self._build_result(value, "down", self.S_neg, timestamp)
            self._reset()
            return result
        
        return None
    
    def _build_result(self, value: float, direction: str, S_value: float, ts: datetime) -> ChangepointResult:
        """构建变点检测结果"""
        if len(self.buffer) >= self.estimation_window:
            pre_window = self.buffer[-2*self.estimation_window:-self.estimation_window]
            post_window = self.buffer[-self.estimation_window:]
            pre_mean = np.mean(pre_window) if pre_window else self.mu_hat
            post_mean = np.mean(post_window) if post_window else value
        else:
            pre_mean = self.mu_hat
            post_mean = value
        
        magnitude = abs(post_mean - pre_mean) / max(abs(pre_mean), 0.001)
        
        # 置信度基于CUSUM统计量超过阈值的程度
        confidence = min(S_value / (self.h * 2), 1.0)
        
        # 过滤过小的变动
        if magnitude < self.min_change:
            confidence *= (magnitude / self.min_change)
        
        return ChangepointResult(
            timestamp=ts,
            confidence=confidence,
            magnitude=magnitude,
            direction=direction,
            pre_mean=pre_mean,
            post_mean=post_mean,
            detection_lag_ms=0  # 由外部填充
        )
    
    def _reset(self):
        """变点检测后重置CUSUM状态"""
        self.S_pos = 0.0
        self.S_neg = 0.0
```

### 6.4 PELT 多变点检测算法

**算法原理：**

Pruned Exact Linear Time (PELT) 是一种精确的多变点检测算法，使用动态规划在 O(n) 时间内找到最优分割点集合：

```
优化目标: min F(s) = Σ C(y[τᵢ₋₁:τᵢ]) + β·K
其中: C = 分段代价函数（负对数似然）
      β = 惩罚项（控制变点数量）
      K = 变点数量
```

```python
from typing import List, Tuple
import numpy as np
from numba import jit  # 用于加速核心循环

class PELTChangepointDetector:
    """
    PELT多变点检测器
    
    用于在较长时间窗口内检测多个结构突变点，
    适用于赛后分析：回顾整场比赛的赔率演变。
    """
    
    def __init__(
        self,
        penalty: float = 10.0,       # β: 拒绝变点的惩罚力度
        min_segment_length: int = 5, # 最小段长 (数据点数)
        model: str = "normal"        # 代价函数模型: normal, gamma, poisson
    ):
        self.penalty = penalty
        self.min_seg_len = min_segment_length
        self.model = model
    
    def detect(self, 
               values: np.ndarray, 
               timestamps: np.ndarray
               ) -> List[ChangepointResult]:
        """
        在完整序列上运行PELT，返回所有检测到的变点
        
        Args:
            values: 赔率值序列
            timestamps: 对应的时间戳
        Returns:
            变点列表，按时间排序
        """
        n = len(values)
        if n < 2 * self.min_seg_len:
            return []
        
        # 预处理: 计算累积和（加速代价计算）
        cumsum = np.cumsum(values)
        cumsum2 = np.cumsum(values ** 2)
        
        # PELT 动态规划核心
        # F[t] = min_{0≤s<t} { F[s] + C(y[s:t]) + β }
        F = np.zeros(n + 1)
        F[0] = -self.penalty  # 初始段
        
        # cp[t] = 最优变点序列中 t 的前驱
        cp = np.zeros(n + 1, dtype=int)
        
        # R = 考虑中的候选变点集（剪枝后）
        R = [0]
        
        for t in range(2 * self.min_seg_len, n + 1):
            # 评估所有候选变点
            best_cost = np.inf
            best_s = t - self.min_seg_len
            
            new_R = []
            for s in R:
                if s > t - self.min_seg_len:
                    new_R.append(s)
                    continue
                
                if s < t - self.min_seg_len:
                    continue
                
                # 计算段的代价
                segment_cost = self._segment_cost(
                    cumsum, cumsum2, s, t
                )
                
                total_cost = F[s] + segment_cost + self.penalty
                
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_s = s
                
                # PELT 剪枝: 如果 F[s] + C(s,t) ≥ F[t*] + C(t*,t), 丢弃 s
                # (简化为基于惩罚项的剪枝)
                if F[s] + segment_cost >= best_cost + self.penalty and s < t - self.min_seg_len:
                    continue
                
                new_R.append(s)
            
            # 添加当前候选
            new_R.append(t - self.min_seg_len)
            R = new_R
            
            F[t] = best_cost
            cp[t] = best_s
        
        # 回溯提取变点
        changepoints = self._backtrack(F, cp, n, values, timestamps)
        
        return changepoints
    
    def _segment_cost(self, cumsum: np.ndarray, cumsum2: np.ndarray, 
                      start: int, end: int) -> float:
        """计算段 y[start:end] 的代价（负对数似然）"""
        if end <= start + 1:
            return 0.0
        
        length = end - start
        
        if self.model == "normal":
            # 正态分布似然代价
            sum_seg = cumsum[end-1] - (cumsum[start-1] if start > 0 else 0)
            sum2_seg = cumsum2[end-1] - (cumsum2[start-1] if start > 0 else 0)
            
            mean = sum_seg / length
            var = sum2_seg / length - mean ** 2
            var = max(var, 1e-10)
            
            # -log L = (n/2)*log(2πσ²) + Σ(x-μ)²/(2σ²)
            # 简化为 n*log(σ)
            return length * np.log(np.sqrt(var))
        
        elif self.model == "gamma":
            # Gamma分布似然代价（赔率通常偏态）
            sample = np.diff(cumsum[start:end])  # 简化
            if len(sample) < 2:
                return 0.0
            mean = np.mean(sample)
            if mean <= 0:
                return np.inf
            return -length * np.log(mean)
        
        return 0.0
    
    def _backtrack(self, F: np.ndarray, cp: np.ndarray, n: int,
                   values: np.ndarray, timestamps: np.ndarray
                   ) -> List[ChangepointResult]:
        """从PELT结果回溯提取变点"""
        changepoints = []
        
        # 从末尾回溯
        t = n
        while t > 0:
            s = cp[t]
            if s > 0 and s < n:
                pre_mean = np.mean(values[max(0, s-10):s])
                post_mean = np.mean(values[s:min(n, s+10)])
                magnitude = abs(post_mean - pre_mean) / max(abs(pre_mean), 0.001)
                
                changepoints.append(ChangepointResult(
                    timestamp=timestamps[s],
                    confidence=0.7,  # PELT无直接置信度
                    magnitude=magnitude,
                    direction="up" if post_mean > pre_mean else "down",
                    pre_mean=pre_mean,
                    post_mean=post_mean,
                    detection_lag_ms=0
                ))
            t = s
        
        return sorted(changepoints, key=lambda cp: cp.timestamp)
```

### 6.5 互相关延迟分析

**数学原理：**

互相关函数 (Cross-Correlation Function, CCF) 用于发现事件时间序列与赔率变动序列之间的最优延迟：

```
CCF(τ) = E[(Eₜ - μₑ)(Oₜ₊τ - μₒ)] / (σₑ · σₒ)

其中: Eₜ = 事件信号（事件发生后 = 1, 否则 = 0）
      Oₜ = 赔率变动信号（Δt 内的对数收益）
      τ = 延迟（lag）
```

```python
import numpy as np
from scipy import signal
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass 
class LagAnalysisResult:
    """延迟分析结果"""
    optimal_lag_seconds: float       # 最优延迟
    correlation_at_lag: float        # 该延迟下的相关系数
    significance_p_value: float      # 显著性
    lag_confidence_interval: Tuple[float, float]  # 95% CI
    alternative_lags: List[Tuple[float, float]]   # 次要峰值

class CrossCorrelationLagAnalyzer:
    """
    互相关延迟分析器
    
    在事件发生前后搜索赔率变动的最强响应窗口，
    确定事件到赔率反应的特征延迟。
    """
    
    def __init__(
        self,
        max_lag_seconds: float = 600.0,     # 最大搜索延迟 (10分钟)
        min_lag_seconds: float = -60.0,     # 最小延迟 (允许前向,检测泄露)
        significance_level: float = 0.05    # 显著性水平
    ):
        self.max_lag = max_lag_seconds
        self.min_lag = min_lag_seconds
        self.alpha = significance_level
    
    def analyze(
        self,
        event_timestamps: List[datetime],
        odds_timeline: List[Tuple[datetime, float]],  # (timestamp, value)
        sampling_interval_ms: float = 100.0  # 重采样间隔
    ) -> LagAnalysisResult:
        """
        分析事件序列与赔率序列之间的最优延迟
        
        步骤:
        1. 将两个序列对齐到统一时间网格
        2. 构建事件信号 (脉冲) 和赔率变动信号 (对数收益)
        3. 计算互相关函数
        4. 找到最大相关的延迟
        5. 评估显著性
        """
        
        # Step 1: 对齐时间网格
        grid_start = min(
            min(event_timestamps) - timedelta(seconds=abs(self.min_lag)),
            odds_timeline[0][0]
        )
        grid_end = max(
            max(event_timestamps) + timedelta(seconds=self.max_lag),
            odds_timeline[-1][0]
        )
        
        n_points = int((grid_end - grid_start).total_seconds() * 1000 / sampling_interval_ms)
        time_grid = np.linspace(
            grid_start.timestamp(), grid_end.timestamp(), n_points
        )
        
        # Step 2a: 构建事件信号
        event_signal = np.zeros(n_points)
        for et in event_timestamps:
            idx = np.argmin(np.abs(time_grid - et.timestamp()))
            if 0 <= idx < n_points:
                # 脉冲 + 指数衰减 (模拟事件影响的持续性)
                decay_tau = 5.0  # 衰减时间常数(秒)
                for i in range(idx, min(idx + 600, n_points)):  # 最多10分钟
                    decay = np.exp(-(i - idx) * sampling_interval_ms / 1000 / decay_tau)
                    if decay < 0.01:
                        break
                    event_signal[i] = max(event_signal[i], decay)
        
        # Step 2b: 构建赔率变动信号 (对数收益)
        odds_values = np.interp(time_grid, 
                                [t.timestamp() for t, _ in odds_timeline],
                                [v for _, v in odds_timeline])
        odds_returns = np.diff(np.log(np.maximum(odds_values, 0.001)))
        odds_returns = np.append(odds_returns, 0)  # 保持长度一致
        
        # Step 3: 计算互相关
        max_lag_points = int(self.max_lag * 1000 / sampling_interval_ms)
        min_lag_points = int(self.min_lag * 1000 / sampling_interval_ms)
        
        lags = np.arange(min_lag_points, max_lag_points + 1)
        correlations = np.zeros(len(lags))
        
        for i, lag in enumerate(lags):
            if lag >= 0:
                # odds 滞后于 event
                corr = np.corrcoef(
                    event_signal[:n_points - lag] if lag > 0 else event_signal,
                    odds_returns[lag:]
                )[0, 1]
            else:
                # event 滞后于 odds (负延迟, 检测信息泄露)
                lag_pos = -lag
                corr = np.corrcoef(
                    event_signal[lag_pos:],
                    odds_returns[:n_points - lag_pos]
                )[0, 1]
            correlations[i] = corr if not np.isnan(corr) else 0
        
        # Step 4: 找到最优延迟
        best_idx = np.argmax(np.abs(correlations))
        best_lag_points = lags[best_idx]
        best_lag_seconds = best_lag_points * sampling_interval_ms / 1000.0
        
        # Step 5: 显著性检验 (基于白噪声假设)
        # H₀: 相关系数 = 0
        # t = r * sqrt((n-2)/(1-r²)) ~ t(n-2)
        r = correlations[best_idx]
        n_eff = n_points - abs(best_lag_points)
        if n_eff > 2 and abs(r) < 1:
            t_stat = r * np.sqrt((n_eff - 2) / (1 - r**2))
            from scipy.stats import t
            p_value = 2 * (1 - t.cdf(abs(t_stat), n_eff - 2))
        else:
            p_value = 1.0
        
        # 置信区间
        # Fisher Z变换: z = arctanh(r) ≈ N(arctanh(ρ), 1/(n-3))
        z = np.arctanh(max(min(r, 0.9999), -0.9999))
        se = 1.0 / np.sqrt(n_eff - 3)
        z_ci = (z - 1.96 * se, z + 1.96 * se)
        lag_ci = (
            best_lag_seconds - 1.96 * sampling_interval_ms / 1000,
            best_lag_seconds + 1.96 * sampling_interval_ms / 1000
        )
        
        # 次要峰值
        alt_lags = self._find_secondary_peaks(lags, correlations, best_idx)
        
        return LagAnalysisResult(
            optimal_lag_seconds=best_lag_seconds,
            correlation_at_lag=correlations[best_idx],
            significance_p_value=p_value,
            lag_confidence_interval=lag_ci,
            alternative_lags=alt_lags
        )
    
    def _find_secondary_peaks(
        self, lags: np.ndarray, correlations: np.ndarray, 
        best_idx: int, min_distance: int = 100
    ) -> List[Tuple[float, float]]:
        """找次要峰值"""
        peaks = []
        sorted_indices = np.argsort(-np.abs(correlations))
        
        for idx in sorted_indices:
            if idx == best_idx:
                continue
            if abs(lags[idx] - lags[best_idx]) < min_distance:
                continue
            if abs(correlations[idx]) < 0.3:  # 最小阈值
                continue
            
            peaks.append((
                lags[idx] * 100 / 1000.0,  # 转为秒
                correlations[idx]
            ))
            
            if len(peaks) >= 3:
                break
        
        return peaks
```

### 6.6 ML关联模型

```python
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

class MLCorrelationModel:
    """
    基于XGBoost的关联预测模型
    
    特征工程覆盖四个维度:
    1. 事件特征 (event_type, severity, entities)
    2. 赔率上下文 (pre-event trend, volatility, volume)
    3. 时间特征 (hour_of_day, days_to_match, is_live)
    4. 市场特征 (bookmaker_count, market_type, spread_width)
    """
    
    # 特征定义
    FEATURE_COLUMNS = [
        # === 事件特征 ===
        "event_severity",              # 事件严重度 1-4
        "event_type_embedding",        # 事件类型Embedding (PCA→3维)
        "entity_count",                # 关联实体数
        "is_live_event",               # 是否为赛中事件
        
        # === 赔率上下文 ===
        "pre_event_trend_slope",       # 事件前趋势斜率 (60s)
        "pre_event_volatility",        # 事件前波动率
        "pre_event_volume_zscore",     # 事件前成交量Z-score
        "odds_level",                  # 当前赔率水平 (1-100)
        
        # === 时间特征 ===
        "hour_of_day_sin",             # 小时 (sin变换, 处理周期)
        "hour_of_day_cos",
        "seconds_to_kickoff",          # 距开球秒数
        "is_in_play",                  # 是否赛中
        
        # === 市场特征 ===
        "bookmaker_count",             # 活跃博彩公司数
        "bookmaker_dispersion",        # 博彩公司间分歧度
        "market_type_h2h",             # One-hot: 1X2
        "market_type_ah",              # One-hot: 亚洲盘
        "market_type_ou",              # One-hot: 大小球
        "spread_width",                # 买-卖价差
    ]
    
    def __init__(self):
        self.model = xgb.XGBClassifier(
            objective='binary:logistic',
            max_depth=6,
            learning_rate=0.05,
            n_estimators=200,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=10,
            scale_pos_weight=3.0,      # 正样本少 (关联事件稀疏)
            eval_metric=['logloss', 'auc']
        )
        self.scaler = StandardScaler()
        self._fitted = False
    
    def extract_features(
        self,
        event: EventRecord,
        odds_timeline: List[OddsRecord],
        time_context: dict
    ) -> np.ndarray:
        """从原始数据提取特征向量"""
        features = []
        
        # 事件特征
        features.append(event.severity.value)
        # 事件类型 → 嵌入 (简化: 使用预训练查表)
        features.extend(self._get_event_embedding(event.event_type))
        features.append(len(event.entities))
        features.append(1 if event.event_type in ("goal", "red_card", "penalty_awarded") else 0)
        
        # 赔率上下文 (事件发生时间点前后)
        event_ts = event.timestamp
        pre_window = [r for r in odds_timeline 
                      if event_ts - timedelta(seconds=60) <= r.timestamp <= event_ts]
        post_window = [r for r in odds_timeline
                       if event_ts < r.timestamp <= event_ts + timedelta(seconds=60)]
        
        if pre_window and len(pre_window) >= 3:
            pre_values = [r.odds_value for r in pre_window]
            pre_times = np.arange(len(pre_values))
            slope = np.polyfit(pre_times, pre_values, 1)[0]
            features.append(slope)
            features.append(np.std(pre_values) / max(np.mean(pre_values), 0.001))
            features.append(
                (np.mean([r.volume or 0 for r in pre_window]) - self.global_mean_volume) 
                / max(self.global_std_volume, 0.001)
            )
        else:
            features.extend([0, 0, 0])
        
        features.append(np.mean([r.odds_value for r in pre_window]) if pre_window else 1.0)
        
        # 时间特征
        hour = event.timestamp.hour
        features.append(np.sin(2 * np.pi * hour / 24))
        features.append(np.cos(2 * np.pi * hour / 24))
        features.append((time_context.get("kickoff", event_ts) - event_ts).total_seconds())
        features.append(1 if time_context.get("is_live", False) else 0)
        
        # 市场特征
        bookmakers = set(r.bookmaker for r in odds_timeline)
        features.append(len(bookmakers))
        features.append(self._calc_dispersion(pre_window) if pre_window else 0)
        features.append(1 if event.metadata.get("market") == "h2h" else 0)
        features.append(1 if event.metadata.get("market") == "asian_handicap" else 0)
        features.append(1 if event.metadata.get("market") == "over_under" else 0)
        features.append(event.metadata.get("spread_width", 0))
        
        return np.array(features, dtype=np.float32)
    
    def predict_correlation(
        self,
        event: EventRecord,
        odds_timeline: List[OddsRecord],
        time_context: dict
    ) -> Tuple[float, float]:
        """
        预测事件与赔率曲线的关联概率
        
        Returns:
            (correlation_probability, confidence)
        """
        X = self.extract_features(event, odds_timeline, time_context)
        X_scaled = self.scaler.transform(X.reshape(1, -1))
        
        proba = self.model.predict_proba(X_scaled)[0]
        correlation_prob = proba[1]  # P(class=1|X)
        
        # 置信度基于预测概率的边距
        margin = abs(correlation_prob - 0.5) * 2
        confidence = margin
        
        return correlation_prob, confidence
    
    def _get_event_embedding(self, event_type: str) -> List[float]:
        """获取事件类型的预训练嵌入向量"""
        # 实际部署中从向量数据库加载; 此处为静态映射
        EMBEDDINGS = {
            "goal": [0.8, 0.1, 0.3],
            "red_card": [0.7, 0.15, 0.5],
            "injury_announcement": [0.4, 0.0, 0.2],
            "yellow_card": [0.2, 0.05, 0.15],
            "substitution": [0.15, 0.0, 0.1],
            "transfer_rumor": [0.1, 0.3, 0.05],
            "manager_change": [0.5, 0.4, 0.3],
            "starting_xi_announced": [0.3, 0.0, 0.25],
        }
        return EMBEDDINGS.get(event_type, [0.0, 0.0, 0.0])
    
    def _calc_dispersion(self, window: List[OddsRecord]) -> float:
        """计算博彩公司间赔率分歧度"""
        if not window:
            return 0.0
        values = [r.odds_value for r in window]
        return np.std(values) / max(np.mean(values), 0.001) if len(values) > 1 else 0.0
```

### 6.7 关联评分与排序

**混合评分策略：**

```python
class CorrelationScorer:
    """
    多方法融合的关联评分器
    
    综合三种检测方法的输出，生成最终关联分数：
    Score = w₁ × S_changepoint + w₂ × S_window + w₃ × S_ml
    
    权重根据数据质量动态调整：
    - 高频数据充足 → CUSUM权重高
    - 数据稀疏 → 事件窗口权重高
    - 有标记训练数据 → ML权重高
    """
    
    def __init__(self):
        self.default_weights = {
            "changepoint": 0.40,
            "event_window": 0.35,
            "ml": 0.25
        }
    
    def score(
        self,
        changepoint_results: List[ChangepointResult],
        window_results: List[WindowAnalysisResult],
        ml_result: Optional[Tuple[float, float]],
        data_quality: DataQualityProfile
    ) -> List[CorrelationCandidate]:
        """
        综合评分并排序关联候选
        
        Args:
            changepoint_results: CUSUM变点检测结果
            window_results: 事件窗口分析结果
            ml_result: ML模型预测 (prob, confidence)
            data_quality: 数据质量档案
        Returns:
            排序后的关联候选列表
        """
        
        # 动态权重调整
        weights = self._adjust_weights(data_quality)
        
        candidates = []
        
        for cp in changepoint_results:
            # 找到时间上最匹配的窗口分析结果
            matching_window = self._find_matching_window(cp.timestamp, window_results)
            
            # 三级评分融合
            cp_score = cp.confidence * cp.magnitude
            win_score = matching_window.score if matching_window else 0.0
            ml_score = ml_result[0] if ml_result else 0.0
            ml_conf = ml_result[1] if ml_result else 0.0
            
            # 融合公式
            combined_score = (
                weights["changepoint"] * cp_score +
                weights["event_window"] * win_score +
                weights["ml"] * ml_score * ml_conf
            )
            
            # 方向一致性奖励
            if matching_window and cp.direction == matching_window.direction:
                combined_score *= 1.1  # +10% 奖励
            if ml_result and cp.direction == ("up" if ml_result[0] > 0.5 else "down"):
                combined_score *= 1.05
            
            # 幅度-延迟联合评分
            # 大变动 + 短延迟 = 高可信度
            latency_factor = self._latency_bonus(matching_window)
            
            final_score = combined_score * latency_factor
            
            candidates.append(CorrelationCandidate(
                timestamp=cp.timestamp,
                score=min(final_score, 1.0),
                magnitude=cp.magnitude,
                direction=cp.direction,
                detection_methods=self._used_methods(cp, matching_window, ml_result),
                components={
                    "changepoint_score": cp_score,
                    "window_score": win_score,
                    "ml_score": ml_score
                }
            ))
        
        # 去重: 同一时间窗口内只保留最高分
        candidates = self._deduplicate_temporal(
            sorted(candidates, key=lambda c: c.score, reverse=True),
            window_seconds=30
        )
        
        return candidates
    
    def _adjust_weights(self, dq: DataQualityProfile) -> dict:
        """根据数据质量动态调整权重"""
        weights = self.default_weights.copy()
        
        # 数据密度低 → 降低CUSUM权重
        if dq.data_density < 0.5:  # 每10秒不足1个tick
            weights["changepoint"] -= 0.15
            weights["event_window"] += 0.15
        
        # 有充足训练数据 → 提高ML权重
        if dq.ml_training_samples > 5000:
            weights["ml"] += 0.10
            weights["changepoint"] -= 0.05
            weights["event_window"] -= 0.05
        
        # 正常化
        total = sum(weights.values())
        return {k: v/total for k, v in weights.items()}
    
    def _latency_bonus(self, window_result: Optional[WindowAnalysisResult]) -> float:
        """延迟奖励因子: 短延迟 → 高可信度"""
        if not window_result or window_result.lag_seconds is None:
            return 1.0
        
        lag = window_result.lag_seconds
        
        if lag <= 30:
            return 1.3       # 30秒内反应: +30%
        elif lag <= 120:
            return 1.15      # 2分钟内: +15%
        elif lag <= 300:
            return 1.0       # 5分钟内: 正常
        elif lag <= 600:
            return 0.85      # 10分钟: -15%
        else:
            return 0.6       # 超过10分钟: -40%
    
    def _deduplicate_temporal(
        self, 
        candidates: List[CorrelationCandidate], 
        window_seconds: float
    ) -> List[CorrelationCandidate]:
        """时间窗口去重"""
        kept = []
        for c in candidates:
            if not any(
                abs((c.timestamp - k.timestamp).total_seconds()) < window_seconds
                for k in kept
            ):
                kept.append(c)
        return kept
```

### 6.8 关联回测与验证框架

```python
class CorrelationBacktester:
    """
    关联引擎回测框架
    
    使用已知关联的历史数据验证引擎准确性:
    1. 准备标注数据集 (已知事件-赔率关联)
    2. 运行关联引擎
    3. 比较检测结果与标注
    4. 计算 Precision, Recall, F1, MAP
    """
    
    def __init__(self, engine: EventOddsCorrelationEngine):
        self.engine = engine
    
    async def run_backtest(
        self,
        test_dataset: List[LabeledMatchData],
        tolerance_seconds: float = 30.0  # 时间容差
    ) -> BacktestReport:
        """
        运行回测并生成报告
        
        Args:
            test_dataset: 标注数据集
                - events: 已知事件列表
                - odds: 完整赔率时间线
                - labels: 人工标注的真实关联 [(event_id, curve_id, timestamp), ...]
            tolerance_seconds: 时间容差 (检测时间与标注时间的允许偏差)
        """
        all_predictions = []
        all_labels = []
        
        for match_data in test_dataset:
            # 运行关联检测
            detected = await self.engine.detect_correlations(
                events=match_data.events,
                odds_series=match_data.odds_by_curve,
                time_window=match_data.time_window,
                methods=["changepoint", "event_window", "ml"]
            )
            
            # 对齐预测与标注
            for label in match_data.labels:
                # 找时间上最接近的检测结果
                best_match = None
                best_distance = float('inf')
                
                for d in detected:
                    distance = abs((d.timestamp - label.timestamp).total_seconds())
                    if distance < tolerance_seconds and distance < best_distance:
                        # 检查是否匹配同一事件和曲线
                        if d.event_id == label.event_id and d.curve_id == label.curve_id:
                            best_match = d
                            best_distance = distance
                
                all_predictions.append(best_match)
                all_labels.append(label)
        
        # 计算指标
        tp = sum(1 for p, l in zip(all_predictions, all_labels) 
                 if p is not None and p.correlation_score >= 0.5)
        fp = len([d for d in all_predictions if d is not None]) - tp  # 简化
        fn = sum(1 for p in all_predictions if p is None)
        
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 0.001)
        
        return BacktestReport(
            precision=precision,
            recall=recall,
            f1_score=f1,
            total_matches=len(test_dataset),
            per_event_type_metrics=self._per_type_metrics(all_predictions, all_labels),
            latency_metrics=self._latency_metrics(all_predictions, all_labels),
            confidence_calibration=self._calibration_curve(all_predictions, all_labels)
        )

class BacktestReport:
    precision: float
    recall: float
    f1_score: float
    total_matches: int
    per_event_type_metrics: Dict[str, Dict[str, float]]
    latency_metrics: Dict[str, float]    # mean, median, p95, p99
    confidence_calibration: List[Tuple[float, float]]
```

### 6.9 价值投注检测数学

**数学原理：**

价值投注 (Value Bet) 存在于当模型估计的真实概率高于市场隐含概率时：

```
Value = P_model(outcome) - P_market(outcome)
+EV = Value > 0

Kelly Criterion 最优投注比例:
f* = (b × p - q) / b
其中: b = Decimal Odds - 1
      p = P_model(outcome)
      q = 1 - p
```

```python
@dataclass
class ValueBetOpportunity:
    match_id: str
    bookmaker: str
    market: str
    selection: str
    market_odds: float              # 市场赔率 (Decimal)
    market_implied_prob: float       # 市场隐含概率
    model_prob: float                # 模型概率
    edge_pct: float                  # 优势百分比
    kelly_fraction: float            # Kelly最优比例
    expected_value: float            # 期望收益
    confidence: float
    timestamp: datetime

class ValueBetDetector:
    """
    价值投注检测器
    
    方法:
    1. 委托-代理模型: 使用博彩公司的平均隐含概率作为"市场共识"
    2. 识别偏离共识的博彩公司
    3. 结合团队实力模型 (ELO, 近期战绩, 阵容强度)
    4. 计算真实概率与市场概率的偏差
    """
    
    def __init__(self, team_model: TeamStrengthModel):
        self.team_model = team_model
        self.min_edge = 0.02          # 最小优势 2%
        self.max_kelly = 0.25         # 最大Kelly比例 (1/4 Kelly)
    
    def detect(
        self,
        match_id: str,
        home_team: str,
        away_team: str,
        odds_snapshot: List[OddsRecord],  # 最新赔率快照
    ) -> List[ValueBetOpportunity]:
        """检测价值投注机会"""
        
        # Step 1: 计算模型概率
        model_probs = self.team_model.predict_match(
            home_team=home_team,
            away_team=away_team,
            context=self._build_context(match_id)
        )
        # model_probs = {"home": 0.45, "draw": 0.25, "away": 0.30}
        
        opportunities = []
        
        # Step 2: 对比每个博彩公司的赔率
        for bookmaker in self._unique_bookmakers(odds_snapshot):
            for record in odds_snapshot:
                if record.bookmaker != bookmaker:
                    continue
                
                # 映射 selection → model outcome
                outcome = self._map_selection_to_outcome(record.selection)
                model_prob = model_probs.get(outcome, 0)
                
                if model_prob <= 0:
                    continue
                
                # 市场隐含概率 (去margin)
                market_prob = self._remove_margin(record, odds_snapshot, bookmaker)
                
                # 计算优势
                edge = model_prob - market_prob
                
                if edge > self.min_edge:
                    # Kelly Criterion
                    b = record.odds_value - 1  # Decimal赔率 → 净赔率
                    p = model_prob
                    q = 1 - p
                    
                    kelly_full = (b * p - q) / max(b, 0.001)
                    kelly_fraction = min(kelly_full * 0.25, self.max_kelly)
                    
                    # 期望收益
                    ev = p * (record.odds_value - 1) - (1 - p) * 1
                    
                    opportunities.append(ValueBetOpportunity(
                        match_id=match_id,
                        bookmaker=bookmaker,
                        market=record.market,
                        selection=record.selection,
                        market_odds=record.odds_value,
                        market_implied_prob=market_prob,
                        model_prob=model_prob,
                        edge_pct=edge * 100,
                        kelly_fraction=kelly_fraction,
                        expected_value=ev,
                        confidence=self._confidence(model_prob, edge),
                        timestamp=datetime.utcnow()
                    ))
        
        # 按期望价值排序
        return sorted(opportunities, key=lambda o: o.expected_value, reverse=True)
    
    def _remove_margin(
        self, 
        record: OddsRecord, 
        all_records: List[OddsRecord],
        bookmaker: str
    ) -> float:
        """去除博彩公司margin，计算真实隐含概率"""
        if record.market != "h2h":
            # 非1X2市场: 直接取倒数
            return 1.0 / record.odds_value
        
        # 1X2市场: 按比例去除margin
        same_market = [
            r for r in all_records 
            if r.bookmaker == bookmaker and r.market == "h2h" and r.match_id == record.match_id
        ]
        
        # 计算margin
        raw_probs = [1.0 / r.odds_value for r in same_market]
        margin = sum(raw_probs) - 1.0
        
        # 按比例分配margin
        raw_prob = 1.0 / record.odds_value
        true_prob = raw_prob / (1.0 + margin)
        
        return true_prob
    
    def _confidence(self, model_prob: float, edge: float) -> float:
        """计算置信度"""
        confidence = 0.5
        
        # 概率越极端，模型越确定
        prob_confidence = abs(model_prob - 0.5) * 2  # 0-1
        confidence += prob_confidence * 0.3
        
        # edge越大越可靠
        edge_confidence = min(edge / 0.1, 1.0)
        confidence += edge_confidence * 0.2
        
        return min(confidence, 1.0)
```

### 6.10 蒙特卡洛模拟架构

```python
@dataclass
class SimulationConfig:
    n_simulations: int = 10000
    random_seed: int = 42
    include_injuries: bool = True
    include_form: bool = True
    include_h2h: bool = True
    decay_factor: float = 0.85    # 历史权重衰减

class MonteCarloBracketSimulator:
    """
    赛事淘汰赛模拟器
    
    模拟流程:
    1. 根据小组赛结果确定淘汰赛对阵
    2. 对每场比赛采样结果 (基于球队实力+随机扰动)
    3. 推进胜者进入下一轮
    4. 重复N次，统计每队各阶段出现频率
    """
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.rng = np.random.RandomState(config.random_seed)
    
    def simulate_tournament(
        self,
        bracket: List[List[TeamProfile]],
        odds_provider: OddsProviderAdapter
    ) -> SimulationResults:
        """
        模拟完整赛事
        
        Args:
            bracket: 淘汰赛对阵表 [[[A1,B2], [C1,D2]], ...]
            odds_provider: 赔率数据源
        Returns:
            模拟结果 (各队夺冠概率、每轮晋级概率)
        """
        n_teams = sum(len(m) for match in self._flatten_bracket(bracket) for m in [match])
        # 每队每轮计数
        round_counts = {
            team.id: [0] * self._n_rounds(bracket)
            for match in self._flatten_bracket(bracket)
            for team in match
        }
        champion_counts = defaultdict(int)
        
        for sim in range(self.config.n_simulations):
            current_round = bracket
            
            for round_idx in range(self._n_rounds(bracket)):
                next_round = []
                
                for match_pair in current_round:
                    winners = []
                    for match in (match_pair if isinstance(match_pair[0], list) else [match_pair]):
                        team_a, team_b = match
                        
                        # 采样比赛结果
                        winner = self._sample_match(team_a, team_b, round_idx)
                        winners.append(winner)
                        
                        # 记录晋级
                        round_counts[winner.id][round_idx] += 1
                    
                    next_round.append(winners)
                
                current_round = next_round
            
            # 冠军
            champion = current_round[0][0]
            champion_counts[champion.id] += 1
        
        # 计算概率
        n = self.config.n_simulations
        return SimulationResults(
            champion_probs={tid: c/n for tid, c in champion_counts.items()},
            round_probs={
                tid: [c/n for c in counts]
                for tid, counts in round_counts.items()
            },
            n_simulations=n
        )
    
    def _sample_match(
        self, team_a: TeamProfile, team_b: TeamProfile, round_idx: int
    ) -> TeamProfile:
        """采样单场比赛结果"""
        
        # 基础实力评分 (ELO级别)
        strength_a = team_a.elo_rating
        strength_b = team_b.elo_rating
        
        # 调整因素
        if self.config.include_form:
            strength_a += team_a.recent_form * 50
            strength_b += team_b.recent_form * 50
        
        if self.config.include_injuries:
            strength_a *= team_a.injury_factor
            strength_b *= team_b.injury_factor
        
        # 主场优势 (中立场地除外)
        home_advantage = 30 if team_a.is_home else (30 if team_b.is_home else 0)
        if team_a.is_home:
            strength_a += home_advantage
        elif team_b.is_home:
            strength_b += home_advantage
        
        # Logit模型: P(A wins) = 1 / (1 + exp(-(strength_a - strength_b) / scale))
        strength_diff = (strength_a - strength_b) / 400.0  # ELO标准尺度
        prob_a = 1.0 / (1.0 + np.exp(-strength_diff * np.log(10)))
        
        # 随机采样
        return team_a if self.rng.random() < prob_a else team_b
    
    def _n_rounds(self, bracket) -> int:
        """计算淘汰赛轮次数"""
        n = 0
        current = bracket
        while isinstance(current, list) and len(current) > 0:
            n += 1
            if isinstance(current[0], list):
                current = current[0]
            else:
                break
        return n
```

### 6.11 市场效率分析

```python
class MarketEfficiencyAnalyzer:
    """
    市场效率分析器
    
    回答核心问题: 事件发生后市场多快完成重新定价？
    
    分析维度:
    1. 定价速度: 事件→赔率稳定的时间
    2. 定价准确性: 调整后的赔率是否反映真实概率
    3. 信息泄露: 事件前是否有异常赔率变动
    """
    
    def analyze_event_efficiency(
        self,
        event: EventRecord,
        odds_timeline: List[OddsRecord],
        final_outcome: Optional[str] = None  # 实际结果
    ) -> MarketEfficiencyReport:
        """分析单个事件的市场效率"""
        
        event_ts = event.timestamp
        
        # 1. 定价速度分析
        pre_event = [r for r in odds_timeline if r.timestamp < event_ts]
        post_event = [r for r in odds_timeline if r.timestamp >= event_ts]
        
        # 计算赔率稳定时间 (变动幅度 < 0.5% 持续30秒)
        stability_time = self._find_stability_time(post_event)
        
        # 2. 信息泄露检测
        # 事件前60秒是否有异常变动
        pre_leak = self._detect_pre_event_leak(pre_event[-60:] if pre_event else [])
        
        # 3. 定价幅度
        if pre_event and post_event:
            pre_avg = np.mean([r.odds_value for r in pre_event[-10:]])
            post_stable = self._get_stable_price(post_event)
            adjustment_pct = (post_stable - pre_avg) / pre_avg * 100
        else:
            adjustment_pct = 0
        
        # 4. 准确性 (如有实际结果)
        if final_outcome:
            post_implied = 1.0 / post_event[-1].odds_value if post_event else None
            accuracy = 1.0 if (
                (final_outcome == "home" and adjustment_pct < 0) or
                (final_outcome == "away" and adjustment_pct > 0)
            ) else 0.0
        else:
            accuracy = None
        
        return MarketEfficiencyReport(
            event_id=event.id,
            stability_time_seconds=stability_time,
            adjustment_pct=adjustment_pct,
            pre_event_leak_detected=pre_leak,
            pricing_accuracy=accuracy,
            efficiency_score=self._calc_efficiency_score(
                stability_time, pre_leak, accuracy
            )
        )
    
    def _find_stability_time(self, post_events: List[OddsRecord]) -> float:
        """找到赔率稳定的时间点"""
        if len(post_events) < 10:
            return float('inf')
        
        values = np.array([r.odds_value for r in post_events])
        # 滚动标准差
        window = 10
        for i in range(window, len(values)):
            rolling_std = np.std(values[i-window:i]) / np.mean(values[i-window:i])
            if rolling_std < 0.005:  # 变动 < 0.5%
                return (post_events[i].timestamp - post_events[0].timestamp).total_seconds()
        
        return (post_events[-1].timestamp - post_events[0].timestamp).total_seconds()
    
    def _detect_pre_event_leak(self, pre_window: List[OddsRecord]) -> bool:
        """检测事件前的异常变动（信息泄露）"""
        if len(pre_window) < 20:
            return False
        
        values = [r.odds_value for r in pre_window]
        # 检查是否有超过3σ的异常变动
        returns = np.diff(np.log(values))
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        
        if std_ret == 0:
            return False
        
        z_scores = abs((returns - mean_ret) / std_ret)
        return any(z > 3.0 for z in z_scores[-10:])  # 最后10个数据点
    
    def _calc_efficiency_score(self, stability_time: float, 
                                 leak: bool, accuracy: Optional[float]) -> float:
        """综合效率评分 0-100"""
        score = 100.0
        
        # 稳定性时间惩罚
        if stability_time > 300:
            score -= 30
        elif stability_time > 120:
            score -= 20
        elif stability_time > 60:
            score -= 10
        elif stability_time < 30:
            score += 10
        
        # 信息泄露惩罚
        if leak:
            score -= 25
        
        # 准确性
        if accuracy is not None:
            score += (accuracy - 0.5) * 20
        
        return max(0, min(score, 100))
```

### 6.12 异常检测系统

```python
class AnomalyDetectionEngine:
    """
    多模型异常检测引擎
    
    检测场景:
    1. 无事件驱动的异常赔率变动 (可能: 内幕交易/大额投注)
    2. 数据源异常行为 (数据延迟/缺失/异常值)
    3. 博彩公司行为异常 (与其他博彩公司显著分歧)
    """
    
    def __init__(self):
        # 集成多个检测器
        self.detectors = [
            IsolationForestDetector(),       # 自适应性好
            RollingStatsDetector(),          # 解释性强
            BookmakerConsensusDetector(),    # 跨博彩公司
        ]
    
    async def detect_anomalies(
        self,
        odds_timeline: List[OddsRecord],
        events: List[EventRecord],
        time_window: Tuple[datetime, datetime]
    ) -> List[AnomalyAlert]:
        """检测异常"""
        alerts = []
        
        # 1. 无事件异常变动检测
        event_timestamps = {e.timestamp for e in events}
        for detector in self.detectors[:2]:
            anomalies = await detector.detect(odds_timeline)
            for anomaly in anomalies:
                # 检查是否有对应事件
                has_event = any(
                    abs((anomaly.timestamp - et).total_seconds()) < 120
                    for et in event_timestamps
                )
                if not has_event:
                    alerts.append(AnomalyAlert(
                        type="unexplained_movement",
                        timestamp=anomaly.timestamp,
                        magnitude=anomaly.magnitude,
                        direction=anomaly.direction,
                        bookmaker=anomaly.bookmaker,
                        message=f"检测到未关联事件的异常赔率变动: "
                                f"{anomaly.magnitude*100:.1f}% {anomaly.direction}"
                    ))
        
        # 2. 博彩公司分歧检测
        consensus_alerts = await self.detectors[2].detect(odds_timeline)
        alerts.extend(consensus_alerts)
        
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

class RollingStatsDetector:
    """基于滚动统计的异常检测"""
    
    def __init__(self, window_size: int = 60, z_threshold: float = 3.5):
        self.window_size = window_size
        self.z_threshold = z_threshold
    
    async def detect(self, timeline: List[OddsRecord]) -> List[AnomalyPoint]:
        """基于滚动Z-score的异常检测"""
        anomalies = []
        values = np.array([r.odds_value for r in timeline])
        
        if len(values) < self.window_size:
            return anomalies
        
        for i in range(self.window_size, len(values)):
            window = values[i-self.window_size:i]
            mean = np.mean(window)
            std = np.std(window)
            
            if std < 1e-6:
                continue
            
            z_score = (values[i] - mean) / std
            
            if abs(z_score) > self.z_threshold:
                anomalies.append(AnomalyPoint(
                    timestamp=timeline[i].timestamp,
                    magnitude=abs(values[i] - mean) / mean,
                    direction="up" if values[i] > mean else "down",
                    z_score=z_score,
                    bookmaker=timeline[i].bookmaker
                ))
        
        return anomalies

class BookmakerConsensusDetector:
    """博彩公司共识分歧检测"""
    
    async def detect(self, timeline: List[OddsRecord]) -> List[AnomalyAlert]:
        """
        检测与市场共识显著偏离的博彩公司
        
        方法: 对每个时间点，计算跨博彩公司的赔率分布，
        标记偏离中位数超过3倍MAD的博彩公司。
        """
        alerts = []
        
        # 按时间窗口分组
        groups = self._group_by_time_window(timeline, window_seconds=30)
        
        for ts, records in groups.items():
            if len(records) < 5:  # 需要至少5家博彩公司
                continue
            
            values = np.array([r.odds_value for r in records])
            median = np.median(values)
            mad = np.median(np.abs(values - median))
            
            if mad < 1e-6:
                continue
            
            for r in records:
                z_score_mad = 0.6745 * (r.odds_value - median) / mad
                if abs(z_score_mad) > 3.5:
                    alerts.append(AnomalyAlert(
                        type="bookmaker_divergence",
                        timestamp=ts,
                        magnitude=abs(r.odds_value - median) / median,
                        direction="up" if r.odds_value > median else "down",
                        bookmaker=r.bookmaker,
                        message=f"{r.bookmaker} 显著偏离共识 ({z_score_mad:.1f}σ)"
                    ))
        
        return alerts
```


## 七、用户交互层

### 7.1 核心交互界面

**主界面布局**：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [数据源选择] [时间区间选择] [曲线配置] [事件筛选] [导出]                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  曲线面板 (多曲线叠加)                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  赔率值  ▲                                                             │ │
│  │          │    ●━━━━━━━━━━━━━●━━━━━━━━━━━━━●━━━━━━━━━━━━━●              │ │
│  │          │   ●             │             │             ●              │ │
│  │          │  ●      ┃       │    ┃        │    ┃      ●               │ │
│  │          │ ●       ┃       │    ┃        │    ┃     ●                │ │
│  │          │●────────┸───────┸────┸────────┸────┸────●                 │ │
│  │          └─────────────────────────────────────────────────────────────▶ │ │
│  │           09:00  10:00  11:00  12:00  13:00  14:00  15:00             │ │
│  │           ◆ 事件A  ◆ 事件B        ◆ 事件C         ◆ 事件D             │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  事件时间轴 (独立展示)                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  事件A ──●── 事件B ──────●── 事件C ──●── 事件D                        │ │
│  │  伤停    │  进球         │  红牌        │  点球                        │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  关联详情面板 (点击事件/曲线点后展示)                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  事件: 姆巴佩伤停 (2026-06-23 10:32)                                   │ │
│  │  关联曲线: 法国胜赔率 (Pinnacle)                                       │ │
│  │  赔率变动: 2.10 → 2.35 (+11.9%)                                       │ │
│  │  反应延迟: 47秒                                                        │ │
│  │  关联强度: 0.87                                                        │ │
│  │  [查看详情] [导出数据]                                                 │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 数据源切换交互

用户可通过下拉菜单或配置面板**动态切换**数据源：

```javascript
// 数据源切换UI逻辑
const oddsSourceSelector = {
  current: 'the_odds_api',
  options: [
    { id: 'the_odds_api', label: 'The Odds API', status: 'online', latency: '1.2s' },
    { id: 'sportmonks', label: 'Sportmonks', status: 'online', latency: '0.8s' },
    { id: 'football_data_co_uk', label: 'Football-Data.co.uk', status: 'offline' },
    { id: 'custom_provider', label: '+ 添加自定义数据源' }
  ],
  onSwitch: (newSource) => {
    // 重新加载该曲线数据，使用新数据源
    refreshCurveData(curveId, newSource, timeRange);
  }
};
```

### 7.3 前端技术选型

| 组件 | 推荐技术 | 理由 |
|---|---|---|
| 框架 | React + TypeScript | 生态成熟，类型安全 |
| 图表库 | ECharts / Plotly.js | 支持多曲线叠加、事件标注、交互缩放 |
| 时间轴 | D3.js / Vis.js | 灵活的事件时间轴渲染 |
| 状态管理 | Zustand / Redux Toolkit | 多数据源状态管理 |
| API通信 | GraphQL (Apollo) | 灵活的数据查询，前端可按需获取字段 |

### 7.4 前端数据流架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                      前端数据流架构                                   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    State Layer (Zustand)                      │    │
│  │                                                               │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │    │
│  │  │chartSlice│  │eventSlice│  │filterSlice│  │uiSlice       │ │    │
│  │  │          │  │          │  │          │  │              │ │    │
│  │  │ curves[] │  │ events[] │  │ timeRange│  │ selectedPoint│ │    │
│  │  │ dataPoints│ │ types[] │  │ providers│  │ hoveredEvent  │ │    │
│  │  │ loading  │  │ severity│  │ bookmakers│  │ panelLayout  │ │    │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘ │    │
│  └───────┼─────────────┼─────────────┼───────────────┼──────────┘    │
│          │             │             │               │               │
│  ┌───────▼─────────────▼─────────────▼───────────────▼──────────┐    │
│  │                    Data Access Layer                          │    │
│  │                                                               │    │
│  │  ┌───────────────┐  ┌──────────────┐  ┌───────────────┐     │    │
│  │  │ GraphQL       │  │ WebSocket    │  │ Cache (LRU)   │     │    │
│  │  │ (Apollo)      │  │ (Realtime)   │  │ (500MB)       │     │    │
│  │  │               │  │              │  │               │     │    │
│  │  │ Queries       │  │ Subscriptions│  │ TTL-based     │     │    │
│  │  │ - oddsTimeline│  │ - oddsUpdated│  │ invalidation  │     │    │
│  │  │ - events      │  │ - eventDetect│  │               │     │    │
│  │  │ - correlations│  │ - anomaly    │  │               │     │    │
│  │  └───────────────┘  └──────────────┘  └───────────────┘     │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

**核心状态管理（Zustand Store）：**

```typescript
// store/chartSlice.ts
interface ChartState {
  // 曲线定义
  curves: CurveDefinition[];
  
  // 数据缓存 (按 curveId → timeRange 索引)
  dataCache: Map<string, Map<string, OddsPoint[]>>;
  
  // 加载状态
  loadingCurves: Set<string>;
  loadingProgress: Map<string, number>;  // 0-100
  
  // 视图状态
  timeRange: { start: Date; end: Date };
  viewport: { xMin: number; xMax: number; yMin: number; yMax: number };
  
  // 选中的点
  selectedPoint: { curveId: string; timestamp: Date; value: number } | null;
  
  // 标注
  annotations: Map<string, EventAnnotation[]>;  // curveId → annotations
  
  // Actions
  addCurve: (config: CurveConfigInput) => Promise<void>;
  removeCurve: (curveId: string) => void;
  updateTimeRange: (range: { start: Date; end: Date }) => void;
  fetchData: (curveId: string, range: TimeRange) => Promise<void>;
  setSelectedPoint: (point: SelectedPoint | null) => void;
}

// store/eventSlice.ts
interface EventState {
  events: EventRecord[];
  selectedEventTypes: Set<string>;
  selectedSeverities: Set<EventSeverity>;
  hoveredEventId: string | null;
  pinnedEvents: Set<string>;  // 钉选的事件（始终显示）
  
  // Actions
  fetchEvents: (range: TimeRange) => Promise<void>;
  toggleEventType: (eventType: string) => void;
  setHoveredEvent: (eventId: string | null) => void;
  pinEvent: (eventId: string) => void;
  unpinEvent: (eventId: string) => void;
}

// store/correlationSlice.ts
interface CorrelationState {
  correlations: Map<string, EventOddsCorrelation[]>;  // curveId → correlations
  selectedCorrelation: EventOddsCorrelation | null;
  showCorrelationLines: boolean;  // 是否显示事件-曲线连接线
  
  // Actions
  fetchCorrelations: (curveIds: string[], range: TimeRange) => Promise<void>;
  selectCorrelation: (correlation: EventOddsCorrelation | null) => void;
}
```

### 7.5 交互状态机

```
用户交互状态机:

                    ┌──────────────────────────────────────────┐
                    │             IDLE (默认浏览)               │
                    │  - 显示所有曲线 + 事件标注               │
                    │  - 支持缩放/平移                         │
                    └─────┬──────┬──────┬──────┬──────────────┘
                          │      │      │      │
              点击数据点   │      │悬停事件│      │ 选择时间区间
                          ▼      │      ▼      │        ▼
              ┌──────────────┐   │  ┌──────────────┐  ┌──────────────┐
              │ POINT_SELECT │   │  │ EVENT_HOVER  │  │ RANGE_SELECT │
              │              │   │  │              │  │              │
              │ 显示该点详情 │   │  │ 高亮关联曲线 │  │ 框选放大     │
              │ 高亮关联事件 │   │  │ 显示事件卡片 │  │ 更新区间     │
              │ 十字线联动   │   │  │ 淡化其他     │  │              │
              └──────┬───────┘   │  └──────┬───────┘  └──────┬───────┘
                     │           │         │                 │
              点击其他│   点击    │  移开   │          释放   │
                    ─┼─ 空白     │  ───────┼──              ─┼──
                     │           │         │                 │
                     ▼           │         ▼                 ▼
              ┌──────────────┐   │  ┌──────────────┐  ┌──────────────┐
              │ DETAIL_PANEL │◀──┘  │ IDLE          │  │ IDLE         │
              │              │      │ (恢复默认)    │  │ (新视口)     │
              │ 事件详情     │      └──────────────┘  └──────────────┘
              │ 关联曲线     │
              │ 变点信息     │
              │ 数据导出     │
              └──────────────┘

状态转换规则:
  - 悬停事件时: 关联曲线高亮 + 显示Tooltip, 不影响其他曲线可见性
  - 点击事件时: 锁定详情面板, 显示完整关联信息, 其他曲线淡化(opacity=0.1)
  - 点击曲线点时: 双向联动 —— 高亮该时间点附近的关联事件
  - 框选区间时: 更新 timeRange, 触发数据重新加载
```

**状态机实现：**

```typescript
// hooks/useInteractionState.ts
type InteractionState = 
  | { type: 'IDLE' }
  | { type: 'EVENT_HOVER'; eventId: string; position: { x: number; y: number } }
  | { type: 'POINT_SELECT'; curveId: string; timestamp: Date; value: number }
  | { type: 'RANGE_SELECT'; startX: number; currentX: number }
  | { type: 'DETAIL_PANEL'; eventId: string; correlationIds: string[] };

function useInteractionReducer() {
  const [state, dispatch] = useReducer(interactionReducer, { type: 'IDLE' });
  
  const actions = {
    hoverEvent: (eventId: string, pos: { x: number; y: number }) =>
      dispatch({ type: 'HOVER_EVENT', eventId, pos }),
    
    unhoverEvent: () =>
      dispatch({ type: 'UNHOVER' }),
    
    clickPoint: (curveId: string, ts: Date, value: number) =>
      dispatch({ type: 'CLICK_POINT', curveId, ts, value }),
    
    clickEvent: (eventId: string, corrIds: string[]) =>
      dispatch({ type: 'CLICK_EVENT', eventId, corrIds }),
    
    startRangeSelect: (x: number) =>
      dispatch({ type: 'START_RANGE', x }),
    
    updateRangeSelect: (x: number) =>
      dispatch({ type: 'UPDATE_RANGE', x }),
    
    endRangeSelect: () =>
      dispatch({ type: 'END_RANGE' }),
    
    clearSelection: () =>
      dispatch({ type: 'CLEAR' }),
  };
  
  return { state, ...actions };
}

function interactionReducer(
  state: InteractionState,
  action: InteractionAction
): InteractionState {
  switch (action.type) {
    case 'HOVER_EVENT':
      return { 
        type: 'EVENT_HOVER', 
        eventId: action.eventId, 
        position: action.pos 
      };
    
    case 'UNHOVER':
      return state.type === 'EVENT_HOVER' 
        ? { type: 'IDLE' } 
        : state;
    
    case 'CLICK_POINT':
      return {
        type: 'POINT_SELECT',
        curveId: action.curveId,
        timestamp: action.ts,
        value: action.value
      };
    
    case 'CLICK_EVENT':
      return {
        type: 'DETAIL_PANEL',
        eventId: action.eventId,
        correlationIds: action.corrIds
      };
    
    case 'START_RANGE':
      return { 
        type: 'RANGE_SELECT', 
        startX: action.x, 
        currentX: action.x 
      };
    
    case 'UPDATE_RANGE':
      return state.type === 'RANGE_SELECT'
        ? { ...state, currentX: action.x }
        : state;
    
    case 'END_RANGE':
      // Range selection completed → triggers timeRange update → returns to IDLE
      return { type: 'IDLE' };
    
    case 'CLEAR':
      return { type: 'IDLE' };
    
    default:
      return state;
  }
}
```

### 7.6 图表渲染管道

```
渲染管道 (ECharts 集成):

  数据 ──▶ 数据预处理 ──▶ 坐标映射 ──▶ Canvas渲染 ──▶ 交互层
           │                │           │              │
           ▼                ▼           ▼              ▼
      - 重采样           - 线性      - 曲线         - 事件标记
        (LTTB降采样)       - 对数      - 网格         - 十字线
      - 缺失值插值       - 时间      - 坐标轴       - Tooltip
      - 格式统一                          - 图例     - 缩放条
```

**LTTB降采样算法（保留视觉特征的降采样）：**

```typescript
// utils/downsample.ts
/**
 * Largest Triangle Three Buckets (LTTB) 降采样
 * 将百万级数据点降至数千点用于渲染，同时保留视觉趋势特征
 * 
 * 算法复杂度: O(n)
 * 
 * 原理: 将数据等分为N个桶，每个桶取能形成最大三角形的点
 */
function lttb(
  data: Array<[number, number]>,  // [timestamp_ms, value]
  targetPoints: number
): Array<[number, number]> {
  const dataLength = data.length;
  
  if (dataLength <= targetPoints) {
    return data;
  }
  
  const result: Array<[number, number]> = [];
  // 总是保留第一个点
  result.push(data[0]);
  
  const bucketSize = (dataLength - 2) / (targetPoints - 2);
  
  let a = 0;  // 上一个选中点
  
  for (let i = 0; i < targetPoints - 2; i++) {
    // 计算当前桶的范围
    const bucketStart = Math.floor((i + 1) * bucketSize) + 1;
    const bucketEnd = Math.floor((i + 2) * bucketSize) + 1;
    const avgBucketEnd = Math.min(bucketEnd, dataLength - 1);
    
    // 计算下一个桶的平均点 (用于三角形面积)
    const nextBucketStart = Math.floor((i + 2) * bucketSize) + 1;
    const nextBucketEnd = Math.floor((i + 3) * bucketSize) + 1;
    const nextBucketAvg = averagePoint(data, nextBucketStart, Math.min(nextBucketEnd, dataLength));
    
    // 在当前桶中找到形成最大三角形的点
    let maxArea = -1;
    let maxAreaPoint = bucketStart;
    
    for (let j = bucketStart; j < avgBucketEnd; j++) {
      const area = triangleArea(
        data[a], data[j], nextBucketAvg
      );
      if (area > maxArea) {
        maxArea = area;
        maxAreaPoint = j;
      }
    }
    
    result.push(data[maxAreaPoint]);
    a = maxAreaPoint;
  }
  
  // 总是保留最后一个点
  result.push(data[dataLength - 1]);
  
  return result;
}

function triangleArea(
  p1: [number, number],
  p2: [number, number],
  p3: [number, number]
): number {
  return Math.abs(
    (p1[0] - p3[0]) * (p2[1] - p1[1]) - 
    (p1[0] - p2[0]) * (p3[1] - p1[1])
  ) * 0.5;
}

function averagePoint(
  data: Array<[number, number]>,
  start: number,
  end: number
): [number, number] {
  let sumX = 0, sumY = 0;
  const count = Math.min(end - start, 1);
  if (count <= 0) return data[start] || [0, 0];
  
  const actualEnd = Math.min(end, data.length);
  for (let i = start; i < actualEnd; i++) {
    sumX += data[i][0];
    sumY += data[i][1];
  }
  return [sumX / count, sumY / count];
}
```

**ECharts集成组件：**

```typescript
// components/OddsChart.tsx
interface OddsChartProps {
  curves: CurveDefinition[];
  dataCache: Map<string, OddsPoint[]>;
  annotations: Map<string, EventAnnotation[]>;
  timeRange: { start: Date; end: Date };
  viewport: Viewport;
  interactionState: InteractionState;
  onPointClick: (curveId: string, ts: Date, value: number) => void;
  onEventClick: (eventId: string) => void;
  onViewportChange: (viewport: Viewport) => void;
}

function OddsChart({ curves, dataCache, annotations, ...props }: OddsChartProps) {
  const chartRef = useRef<echarts.ECharts>();
  
  // 构建ECharts配置
  const option = useMemo(() => ({
    // 多X轴 (时间) + 多Y轴 (如需要)
    xAxis: {
      type: 'time',
      min: props.timeRange.start.getTime(),
      max: props.timeRange.end.getTime(),
      axisLabel: { formatter: '{HH}:{mm}:{ss}' }
    },
    yAxis: {
      type: 'value',
      name: '赔率 (Decimal)',
      axisLabel: { formatter: '{value}' }
    },
    
    // 曲线系列
    series: [
      ...curves.map((curve, i) => {
        const data = dataCache.get(curve.id) || [];
        const downsampled = lttb(
          data.map(p => [p.timestamp.getTime(), p.value] as [number, number]),
          2000  // 渲染目标点数
        );
        
        return {
          type: 'line',
          name: curve.name,
          data: downsampled,
          smooth: true,
          symbol: 'none',  // 不显示数据点符号 (性能优化)
          lineStyle: { width: 2, color: CURVE_COLORS[i % CURVE_COLORS.length] },
          // 事件标注 (markPoint)
          markPoint: {
            data: (annotations.get(curve.id) || []).map(a => ({
              name: a.title,
              coord: [a.timestamp.getTime(), a.relatedPoint?.value || 0],
              symbol: 'pin',
              symbolSize: 20,
              itemStyle: { color: SEVERITY_COLORS[a.severity] },
              // 点击事件
              onClick: () => props.onEventClick(a.eventId)
            }))
          }
        };
      }),
      
      // 竖线标注 (事件时间线)
      {
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        polyline: false,
        data: getEventVerticalLines(annotations),
        lineStyle: { type: 'dashed', color: '#999', width: 1 }
      }
    ],
    
    // 交互配置
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },     // 滚轮缩放
      { type: 'slider', start: 0, end: 100, height: 30 }  // 底部滑块
    ],
    toolbox: {
      feature: {
        dataZoom: { yAxisIndex: 'none' },
        restore: {},
        saveAsImage: { pixelRatio: 2 }
      }
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        // 自定义Tooltip: 显示选中点 + 关联事件
        return formatTooltipWithEvents(params, annotations);
      }
    }
  }), [curves, dataCache, annotations, props.timeRange]);
  
  return <EChartsReact ref={chartRef} option={option} 
    style={{ height: '100%', width: '100%' }}
    onEvents={{
      click: handleClick,
      datazoom: handleZoom
    }}
  />;
}
```

### 7.7 事件-曲线关联可视化

**双向联动机制：**

```typescript
// hooks/useEventCurveLinking.ts
/**
 * 事件-曲线联动Hook
 * 
 * 实现三种联动:
 * 1. 悬停事件 → 对应曲线点高亮
 * 2. 点击曲线点 → 关联事件高亮
 * 3. 框选区间 → 区间内事件计数与高亮
 */
function useEventCurveLinking(
  chartRef: RefObject<echarts.ECharts>,
  eventTimelineRef: RefObject<EventTimelineHandle>,
  correlationState: CorrelationState,
  interactionState: InteractionState
) {
  // 联动1: 悬停事件 → 曲线高亮
  useEffect(() => {
    if (interactionState.type !== 'EVENT_HOVER') return;
    
    const { eventId } = interactionState;
    const correlations = findCorrelationsForEvent(eventId, correlationState);
    
    if (correlations.length > 0 && chartRef.current) {
      // 在曲线上高亮关联点
      chartRef.current.dispatchAction({
        type: 'highlight',
        seriesIndex: correlations.map(c => c.curveId)
      });
      
      // 显示十字线对准事件时间
      const event = getEventById(eventId);
      if (event) {
        chartRef.current.dispatchAction({
          type: 'showTip',
          seriesIndex: 0,
          dataIndex: findNearestDataIndex(event.timestamp)
        });
      }
    }
  }, [interactionState]);
  
  // 联动2: 点击曲线点 → 查找关联事件
  const handleChartClick = useCallback((params: any) => {
    if (!params.data) return;
    
    const clickedTime = new Date(params.data[0]);
    // 在时间窗口中搜索关联事件
    const nearbyEvents = findEventsInWindow(
      clickedTime, 
      WINDOW_SECONDS, 
      correlationState
    );
    
    if (nearbyEvents.length > 0) {
      // 通知事件时间轴滚动到对应位置
      eventTimelineRef.current?.scrollToTime(clickedTime);
      // 高亮关联事件
      eventTimelineRef.current?.highlightEvents(nearbyEvents.map(e => e.id));
    }
  }, [correlationState]);
  
  // 联动3: 框选区间 → 事件计数
  const handleZoomChange = useCallback((start: Date, end: Date) => {
    const eventsInRange = countEventsInRange(start, end);
    // 更新事件密度指示器
    dispatch({ type: 'UPDATE_EVENT_DENSITY', count: eventsInRange });
  }, []);
  
  return { handleChartClick, handleZoomChange };
}
```

### 7.8 高级筛选与钻取

**筛选器架构：**

```typescript
// components/filters/FilterEngine.ts
interface FilterState {
  // 时间维度
  timeRange: { start: Date; end: Date };
  matchPhase: 'pre_match' | 'in_play' | 'post_match' | 'all';
  
  // 赔率维度
  providers: Set<string>;        // 数据源
  bookmakers: Set<string>;       // 博彩公司
  markets: Set<string>;          // 市场类型
  oddsRange: { min: number; max: number };  // 赔率范围
  
  // 事件维度
  eventTypes: Set<string>;
  severities: Set<number>;
  confidence: { min: number; max: number };
  
  // 关联维度
  correlationStrength: { min: number };  // 最小关联强度
  lagRange: { min: number; max: number };  // 延迟范围
  direction: 'up' | 'down' | 'both';
}

// 筛选器编译为GraphQL查询
function compileFilterToQuery(filter: FilterState): FilterQuery {
  return {
    oddsInput: {
      timeRange: filter.timeRange,
      providers: [...filter.providers],
      bookmakers: [...filter.bookmakers],
      markets: [...filter.markets],
      oddsValueRange: filter.oddsRange
    },
    eventInput: {
      timeRange: filter.timeRange,
      eventTypes: [...filter.eventTypes],
      severities: [...filter.severities],
      minConfidence: filter.confidence.min
    },
    correlationInput: {
      minScore: filter.correlationStrength.min,
      lagRange: filter.lagRange,
      direction: filter.direction === 'both' ? undefined : filter.direction
    }
  };
}

// 筛选器历史 (支持撤销/重做)
interface FilterHistory {
  past: FilterState[];
  present: FilterState;
  future: FilterState[];
  
  push: (state: FilterState) => void;
  undo: () => FilterState | null;
  redo: () => FilterState | null;
}
```

**钻取路径：**

```
钻取层级:

  Level 0: 赛事全景
  │  多条曲线叠加，所有事件标注
  │
  ├── Level 1: 单事件钻取
  │   │  点击事件 → Detail Panel
  │   │  显示: 事件详情、关联曲线、延迟、幅度
  │   │
  │   └── Level 2: 时间微钻取
  │       │  展开事件前后30秒的逐tick数据
  │       │  显示: 每个tick的赔率值、博彩公司、时间戳
  │       │
  │       └── Level 3: 博彩公司对比
  │           对比不同博彩公司对该事件的反应速度和幅度
  │
  ├── Level 1: 曲线分析钻取
  │   │  点击曲线区域 → 统计面板
  │   │  显示: 均值、波动率、变点分布
  │   │
  │   └── Level 2: 变点列表
  │       所有检测到的变点，按置信度排序
  │
  └── Level 1: 数据源对比钻取
      同一曲线在不同数据源下的表现差异
```

### 7.9 Jupyter Notebook 集成

```python
# analysis/notebook_api.py
"""
Jupyter Notebook 分析接口

提供 Python API 供 Notebook 环境使用，
支持编程式数据查询、关联分析、可视化。
"""

class NotebookAnalysisAPI:
    """Notebook 分析 API"""
    
    def __init__(self, api_url: str = "http://localhost:4000/graphql"):
        self.client = GraphQLClient(api_url)
    
    def query_odds(
        self,
        match_id: str,
        time_range: Tuple[str, str],
        bookmakers: Optional[List[str]] = None,
        markets: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """查询赔率数据并返回Pandas DataFrame"""
        query = """
        query OddsTimeline($input: OddsTimelineInput!) {
          oddsTimeline(input: $input) {
            dataPoints {
              timestamp
              value
              bookmaker
              market
              selection
              impliedProbability
            }
          }
        }
        """
        result = self.client.execute(query, variables={
            "input": {
                "matchId": match_id,
                "timeRange": {
                    "start": time_range[0],
                    "end": time_range[1]
                },
                "bookmakers": bookmakers,
                "markets": markets
            }
        })
        
        df = pd.DataFrame(result["oddsTimeline"]["dataPoints"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        return df
    
    def query_events(
        self,
        match_id: Optional[str] = None,
        time_range: Optional[Tuple[str, str]] = None,
        event_types: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """查询事件数据"""
        ...
    
    def detect_correlations(
        self,
        events: List[str],  # event_ids
        odds_curve_id: str,
        methods: List[str] = ["changepoint", "event_window"]
    ) -> pd.DataFrame:
        """运行关联检测"""
        ...
    
    def plot_with_events(
        self,
        odds_df: pd.DataFrame,
        events_df: pd.DataFrame,
        correlations_df: pd.DataFrame,
        title: str = "赔率-事件关联图"
    ) -> None:
        """
        快速绘制赔率曲线 + 事件标注
        
        使用 Plotly 在 Notebook 中内嵌交互式图表
        """
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            shared_xaxes=True,
            vertical_spacing=0.05
        )
        
        # 赔率曲线
        for bookmaker in odds_df["bookmaker"].unique():
            bm_data = odds_df[odds_df["bookmaker"] == bookmaker]
            fig.add_trace(
                go.Scatter(
                    x=bm_data.index,
                    y=bm_data["value"],
                    mode="lines",
                    name=f"{bookmaker}",
                    hovertemplate="%{x}<br>赔率: %{y:.3f}<extra></extra>"
                ),
                row=1, col=1
            )
        
        # 事件标注
        for _, corr in correlations_df.iterrows():
            fig.add_vline(
                x=corr["timestamp"],
                line_dash="dash",
                line_color="red",
                opacity=0.5,
                annotation_text=corr["event_type"],
                row=1, col=1
            )
        
        # 事件时间轴
        for _, event in events_df.iterrows():
            fig.add_trace(
                go.Scatter(
                    x=[event["timestamp"], event["timestamp"]],
                    y=[0, event["severity"]],
                    mode="lines+markers",
                    name=event["title"],
                    marker=dict(size=8),
                    hovertemplate=event["title"]
                ),
                row=2, col=1
            )
        
        fig.update_layout(
            title=title,
            height=700,
            hovermode="x unified"
        )
        fig.show()
    
    def find_value_bets(
        self,
        match_ids: List[str],
        min_edge_pct: float = 2.0
    ) -> pd.DataFrame:
        """扫描价值投注机会"""
        ...
    
    def simulate_tournament(
        self,
        bracket_template: str = "world_cup_2026",
        n_simulations: int = 10000,
        progress_bar: bool = True
    ) -> pd.DataFrame:
        """运行蒙特卡洛模拟"""
        ...
```


## 八、技术栈总览

| 层级 | 组件 | 推荐技术 | 备选 |
|---|---|---|---|
| **前端** | Web应用 | React + TypeScript + ECharts | Vue + Plotly |
| **API网关** | 接口层 | GraphQL (Apollo Server) | REST + FastAPI |
| **消息队列** | 实时管道 | Apache Kafka | RabbitMQ / Pulsar |
| **流处理** | 实时计算 | Apache Spark Streaming | Flink / RisingWave |
| **批处理** | 离线ETL | Apache Airflow + dbt | Prefect |
| **时序数据库** | 赔率存储 | TimescaleDB | InfluxDB / QuestDB |
| **OLAP** | 分析查询 | Apache Druid | ClickHouse |
| **缓存** | 热数据 | Redis | Memcached |
| **对象存储** | 数据湖 | AWS S3 / MinIO | 阿里云OSS |
| **后端框架** | 业务服务 | Python (FastAPI) | Node.js / Go |
| **容器编排** | 部署 | Kubernetes + Docker | Docker Compose |


## 九、实施路线图

### Phase 1: MVP (4-6周)
- [ ] 实现核心数据模型
- [ ] 接入 **The Odds API** 和 **Football-Data.co.uk** 两个赔率数据源
- [ ] 接入 **sportiq-mcp RAW工具** 作为事件数据源
- [ ] 实现基础的多曲线叠加图表（ECharts）
- [ ] 手动事件标注功能

### Phase 2: 关联引擎 (4-6周)
- [ ] 实现统计变点检测算法
- [ ] 实现事件窗口关联分析
- [ ] 接入 **GDELT** 新闻事件数据源
- [ ] 关联结果可视化（事件-曲线联动高亮）

### Phase 3: 多数据源完善 (3-4周)
- [ ] 接入 **Sportmonks API**
- [ ] 接入 **Unified Odds Feed (Sportradar)**
- [ ] 数据源管理UI（启用/禁用/配置）
- [ ] 数据源优先级与冲突解决

### Phase 4: 高级功能 (4-6周)
- [ ] 实时流处理管道 (Kafka + Spark)
- [ ] 蒙特卡洛模拟集成
- [ ] 价值投注检测
- [ ] 异常预警系统
- [ ] Jupyter Notebook 分析接口

### Phase 5: 生产就绪 (持续)
- [ ] 性能优化与水平扩展
- [ ] 数据质量监控面板
- [ ] 用户权限与多租户
- [ ] API文档与开发者门户


## 十、开源参考项目

以下开源项目可作为系统各模块的参考实现：

| 项目 | 功能 | 参考价值 |
|---|---|---|
| **BetFlow** | 实时体育博彩分析平台 | 整体架构、Kafka+Spark+Druid技术栈 |
| **sportiq-mcp** | AI可调用的体育数据工具 | 数据源聚合、蒙特卡洛模拟、价值投注检测 |
| **sports-skills** | 轻量级体育数据SDK | 多数据源统一封装方式 |
| **The Odds API Python SDK** | 赔率API客户端 | 具体数据源接入参考 |
| **mcp-sports-hub** | 32个体育API聚合 | 大规模数据源管理思路 |


## 十一、安全架构

### 11.1 认证与授权

```
┌──────────────────────────────────────────────────────────────────────┐
│                        安全边界                                       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ 用户      │───▶│ API网关   │───▶│ 认证服务   │───▶│ 权限引擎   │      │
│  │ (Browser) │    │ (Kong)   │    │ (Keycloak)│    │ (OPA)    │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│                                                                      │
│  认证方式:                                                           │
│  - OAuth 2.0 + OIDC (用户登录)                                       │
│  - API Key (程序化访问)                                              │
│  - JWT Bearer Token (服务间通信)                                     │
│  - M2M (Machine-to-Machine) Client Credentials                       │
└──────────────────────────────────────────────────────────────────────┘
```

**权限模型 (RBAC):**

| 角色 | 权限范围 | 说明 |
|---|---|---|
| `admin` | 全部 | 系统管理、数据源配置、用户管理 |
| `analyst` | 读 + 分析 + 导出 | 查看曲线、配置关联引擎、导出报告 |
| `viewer` | 只读 | 查看已配置的曲线和关联结果 |
| `api_consumer` | 程序化读取 | 仅通过API访问，受限速率 |
| `provider_admin` | 数据源管理 | 独立管理特定数据源配置 |

### 11.2 密钥管理

```
密钥生命周期管理:

  生成 ──▶ 存储 ──▶ 轮换 ──▶ 吊销 ──▶ 归档
   │        │        │        │
   │        ▼        ▼        ▼
   │    ┌──────────────────────────┐
   │    │     HashiCorp Vault       │
   │    │  (Secret Engine: kv-v2)  │
   │    └──────────────────────────┘
   │              │
   ▼              ▼
  配置注入     运行时注入
 (K8s Secrets)  (vault-agent sidecar)
```

**密钥分类与策略:**

| 密钥类型 | 存储位置 | 轮换周期 | 访问控制 |
|---|---|---|---|
| 数据源API Key | Vault KV-v2 | 90天 | 仅数据源适配器Pod |
| 用户JWT签名密钥 | Vault Transit | 30天 | 仅认证服务 |
| 数据库凭证 | Vault Database | 动态生成, TTL 24h | 按服务账号 |
| TLS证书 | cert-manager | 自动90天 | K8s Ingress |
| 内部服务密钥 | Vault KV-v2 | 180天 | 按命名空间隔离 |

### 11.3 数据安全

```yaml
# 数据分级
data_classification:
  public:
    - 公开赔率数据
    - 已发布赛事结果
  internal:
    - 聚合统计数据
    - 分析报告
  confidential:
    - 用户行为日志
    - 分析模型参数
  restricted:
    - 用户凭证 (bcrypt哈希存储)
    - API密钥 (加密存储)
    - 支付信息 (如需)

# 传输加密
encryption_in_transit:
  - 外部入口: TLS 1.3 (强制)
  - 服务间通信: mTLS (Istio/Consul Connect)
  - 消息队列: SASL_SSL + 证书认证

# 静态加密
encryption_at_rest:
  - 数据库: AES-256-GCM (TimescaleDB原生加密 / pg_tde)
  - 对象存储: SSE-KMS (S3) / OSS-KMS (阿里云)
  - 消息队列: Kafka端到端加密
  - 备份: 加密后传输至异地
```

### 11.4 API安全

| 防护机制 | 实现 | 参数 |
|---|---|---|
| 速率限制 | Kong rate-limiting 插件 | 用户: 100 req/min; API Key: 500 req/min |
| IP白名单 | Kong IP Restriction | 管理端点仅允许VPN IP段 |
| 请求验证 | JSON Schema 校验 | 拒绝不符合schema的请求 |
| SQL注入防护 | 参数化查询 + ORM | SQLAlchemy 2.0 |
| CORS策略 | 严格白名单 | 仅允许前端域名 |
| WAF | ModSecurity / Coraza | OWASP核心规则集 |


## 十二、可观测性

### 12.1 三大支柱

```
┌──────────────────────────────────────────────────────────────────────┐
│                      可观测性栈                                      │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │    日志 (Logs)   │  │   指标 (Metrics) │  │  追踪 (Traces)  │      │
│  │   Elasticsearch  │  │   Prometheus    │  │   Jaeger        │      │
│  │   + Kibana       │  │   + Grafana     │  │   + OpenTelemetry│     │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘      │
│           │                    │                    │                │
│           ▼                    ▼                    ▼                │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              采集层 (OpenTelemetry Collector)                  │    │
│  │   自动埋点  │  结构化日志  │  Prometheus Exporter  │  SDK     │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### 12.2 关键指标定义

**RED指标 (每服务):**

| 指标 | 类型 | 描述 | 告警阈值 |
|---|---|---|---|
| Request Rate | Counter | 每秒请求数 | > 正常值3σ |
| Error Rate | Gauge | 5xx错误比例 | > 1% (5min窗口) |
| Duration (P50/P95/P99) | Histogram | 请求延迟 | P95 > 500ms |

**USE指标 (每资源):**

| 指标 | 类型 | 描述 | 告警阈值 |
|---|---|---|---|
| CPU Utilization | Gauge | CPU使用率 | > 80% (5min) |
| Memory Usage | Gauge | 内存使用率 | > 85% |
| Disk I/O | Gauge | 磁盘IOPS | > 80% 容量 |
| Network Throughput | Gauge | 网络吞吐 | > 80% 带宽 |

**业务指标:**

| 指标 | 类型 | 描述 |
|---|---|---|
| `odds_data_points_ingested` | Counter | 已入库赔率数据点数 |
| `events_ingested` | Counter | 已入库事件数 |
| `correlation_detections` | Counter | 自动检测到的关联数 |
| `data_source_latency_seconds` | Histogram | 各数据源端到端延迟 |
| `data_source_availability` | Gauge | 数据源可用性 (0/1) |
| `pipeline_lag_seconds` | Gauge | 管道处理延迟 |
| `user_active_sessions` | Gauge | 活跃用户会话数 |

### 12.3 告警规则

```yaml
# prometheus_rules.yaml
groups:
  - name: data_pipeline
    rules:
      - alert: DataSourceDown
        expr: data_source_availability == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "数据源 {{ $labels.provider }} 不可用"
          
      - alert: PipelineLagHigh
        expr: pipeline_lag_seconds > 60
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "管道延迟超过60秒，当前: {{ $value }}s"
          
      - alert: AnomalousOddsMovement
        expr: abs(odds_change_pct) > 20
        for: 1m
        labels:
          severity: info
        annotations:
          summary: "异常赔率变动 {{ $value }}% 检测于 {{ $labels.match_id }}"

  - name: infrastructure
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
          
      - alert: DiskSpaceLow
        expr: disk_free_percent < 20
        for: 10m
        labels:
          severity: warning
```

### 12.4 分布式追踪

```
请求追踪链路 (典型请求):

  Client Request
       │
       ▼
  [API Gateway] ──── span: gateway.proxy (5ms)
       │
       ▼
  [GraphQL Server] ─ span: graphql.resolve (45ms)
       │
       ├──▶ [Data Service] ─ span: data.query (30ms)
       │         │
       │         └──▶ [TimescaleDB] ─ span: db.select (25ms)
       │
       └──▶ [Analytics Engine] ─ span: analytics.correlate (150ms)
                 │
                 └──▶ [Redis Cache] ─ span: cache.get (2ms)

  Trace Context: W3C Trace-Context 标准
  采样策略: 头部采样 (100%错误 + 10%正常请求)
```

### 12.5 健康检查

```python
class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

# 每个服务暴露 /health 端点
# GET /health → 聚合所有依赖的健康状态
{
  "status": "healthy",
  "checks": {
    "database": {"status": "healthy", "latency_ms": 3},
    "redis": {"status": "healthy", "latency_ms": 1},
    "kafka": {"status": "healthy", "lag": 0},
    "data_source:the_odds_api": {"status": "healthy", "last_sync": "2026-06-23T10:00:00Z"},
    "data_source:gdelt": {"status": "degraded", "last_sync": "2026-06-23T09:55:00Z", "error": "rate_limited"}
  }
}
```


## 十三、错误处理与韧性模式

### 13.1 分层错误处理策略

```
┌──────────────────────────────────────────────────────────────────────┐
│                      错误处理层                                      │
│                                                                      │
│  Layer 1: 用户交互层                                                 │
│  - 优雅降级UI (部分数据可用时仍可展示)                                │
│  - 用户友好的错误提示 (非技术语言)                                    │
│  - 自动重试 (UI层最多3次, 指数退避)                                  │
│                                                                      │
│  Layer 2: API/服务层                                                 │
│  - 统一错误码 (RFC 7807 Problem Details)                             │
│  - 请求级重试 (非幂等操作最多1次)                                    │
│  - 熔断器 (5次失败 → OPEN, 30s后 → HALF_OPEN)                       │
│                                                                      │
│  Layer 3: 数据源适配层                                               │
│  - 数据源隔离 (单源故障不影响其他源)                                  │
│  - 降级数据源自动切换 (优先级链)                                     │
│  - 陈旧数据回退 (缓存数据作为兜底)                                   │
│                                                                      │
│  Layer 4: 数据管道层                                                 │
│  - 死信队列 (DLQ) 捕获处理失败消息                                   │
│  - 检查点+回放 (Kafka offset管理)                                   │
│  - 幂等写入 (去重key: provider+source_id+timestamp)                  │
└──────────────────────────────────────────────────────────────────────┘
```

### 13.2 熔断器实现

```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio

class CircuitState(Enum):
    CLOSED = "closed"           # 正常
    OPEN = "open"               # 熔断
    HALF_OPEN = "half_open"     # 探测

@dataclass
class CircuitBreaker:
    """数据源适配器熔断器"""
    failure_threshold: int = 5
    recovery_timeout: float = 30.0   # 秒
    half_open_max_requests: int = 3
    
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    half_open_successes: int = 0
    
    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if self._should_attempt_recovery():
                self.state = CircuitState.HALF_OPEN
                self.half_open_successes = 0
            else:
                raise CircuitBreakerOpenError(
                    f"熔断器开启，{self.recovery_timeout}s后重试"
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= self.half_open_max_requests:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        else:
            self.failure_count = 0
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def _should_attempt_recovery(self) -> bool:
        if self.last_failure_time is None:
            return True
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout
```

### 13.3 数据源降级策略

```python
class DataSourceFallbackManager:
    """数据源降级管理器 —— 按优先级链自动切换"""
    
    async def fetch_with_fallback(
        self,
        request: OddsRequest,
        providers: List[str],  # 按优先级排序
        cache_ttl_fallback: int = 300  # 降级缓存TTL
    ) -> Tuple[List[OddsRecord], str]:  # (数据, 实际使用的数据源)
        
        for provider_id in providers:
            provider = self.registry.get(provider_id)
            if not provider or not provider.is_enabled:
                continue
            
            try:
                result = await provider.fetch_odds(**request.dict())
                return result, provider_id
            except RateLimitError:
                logger.warning(f"{provider_id} 速率限制，尝试下一数据源")
                continue
            except CircuitBreakerOpenError:
                logger.warning(f"{provider_id} 熔断器开启，跳过")
                continue
            except TemporaryError:
                logger.warning(f"{provider_id} 临时错误，尝试下一数据源")
                continue
        
        # 所有数据源失败 → 返回缓存数据（标记为陈旧）
        stale_data = await self.cache.get(request.cache_key)
        if stale_data:
            return stale_data, "cache(stale)"
        
        raise AllProvidersFailedError("所有数据源不可用")
```

### 13.4 错误码体系

```python
# 统一错误码 (RFC 7807 Problem Details)
class ErrorCode:
    # 数据源错误 (DS-xxx)
    DS_PROVIDER_UNAVAILABLE = "DS-001"
    DS_RATE_LIMITED = "DS-002"
    DS_AUTH_FAILED = "DS-003"
    DS_DATA_STALE = "DS-004"
    DS_CIRCUIT_OPEN = "DS-005"
    
    # 查询错误 (QR-xxx)  
    QR_INVALID_TIME_RANGE = "QR-001"
    QR_MATCH_NOT_FOUND = "QR-002"
    QR_TOO_MANY_POINTS = "QR-003"
    
    # 关联错误 (CR-xxx)
    CR_INSUFFICIENT_DATA = "CR-001"
    CR_CONFIDENCE_LOW = "CR-002"
    
    # 系统错误 (SY-xxx)
    SY_INTERNAL = "SY-001"
    SY_TIMEOUT = "SY-002"
    SY_DEGRADED = "SY-003"

# Error Response Example:
# {
#   "type": "https://api.example.com/errors/DS-001",
#   "title": "Data Source Unavailable",
#   "status": 502,
#   "detail": "数据源 'the_odds_api' 当前不可用，已自动切换到 'sportmonks'",
#   "instance": "/api/v1/odds?match_id=xxx",
#   "error_code": "DS-001",
#   "fallback_used": "sportmonks"
# }
```


## 十四、测试策略

### 14.1 测试金字塔

```
           ┌─────┐
           │ E2E │  5%  —— 关键用户旅程 (Playwright)
          ┌┴─────┴┐
          │ 集成   │  15% —— 服务间契约、数据库、消息队列
         ┌┴───────┴┐
         │  组件    │  25% —— 独立服务 + mock依赖
        ┌┴─────────┴┐
        │   单元     │  55% —— 函数、类、模型
        └───────────┘
```

### 14.2 各层测试策略

**单元测试:**

```python
# 示例: 适配器接口合规性测试
class TestOddsAdapterContract:
    """验证所有适配器实现统一接口合约"""
    
    @pytest.mark.parametrize("adapter_class", all_odds_adapters())
    def test_fetch_odds_returns_standard_model(self, adapter_class):
        """所有适配器必须返回标准 OddsRecord 列表"""
        adapter = adapter_class(config=TEST_CONFIG)
        results = await adapter.fetch_odds(match_id="test-001")
        assert all(isinstance(r, OddsRecord) for r in results)
    
    @pytest.mark.parametrize("adapter_class", all_odds_adapters())
    def test_fetch_odds_honors_time_range(self, adapter_class):
        """所有适配器必须支持时间范围过滤"""
        adapter = adapter_class(config=TEST_CONFIG)
        start = datetime(2026, 6, 1)
        end = datetime(2026, 6, 23)
        results = await adapter.fetch_odds(start_time=start, end_time=end)
        assert all(start <= r.timestamp <= end for r in results)
    
    @pytest.mark.parametrize("adapter_class", all_odds_adapters())
    def test_get_supported_markets_non_empty(self, adapter_class):
        """所有适配器必须声明支持的市场类型"""
        adapter = adapter_class(config=TEST_CONFIG)
        markets = adapter.get_supported_markets()
        assert len(markets) > 0
```

**集成测试:**

| 测试场景 | 工具 | 说明 |
|---|---|---|
| 数据库迁移 | pytest + testcontainers | 验证Alembic迁移在真实PostgreSQL上成功 |
| API契约 | pytest + schemathesis | 自动生成测试用例验证API Schema合规 |
| Kafka消息 | pytest + testcontainers-kafka | 验证生产者→消费者消息完整性 |
| 数据源模拟 | WireMock / responses | 模拟外部API响应，测试适配器行为 |
| 缓存一致性 | pytest + fakeredis | 验证Redis缓存逻辑 |

**E2E测试:**

```python
# 关键用户旅程
CRITICAL_JOURNEYS = [
    "用户选择时间区间 → 加载赔率曲线 → 叠加事件标注 → 点击事件查看关联详情",
    "用户切换数据源 → 曲线自动刷新 → 数据源状态更新",
    "用户配置新曲线 → 选择数据源+市场+博彩公司 → 曲线加入面板",
    "用户筛选事件类型 → 事件时间轴更新 → 关联高亮同步",
]
```

### 14.3 测试基础设施

```yaml
# CI测试矩阵
test_pipeline:
  on_push:
    - lint: [ruff, mypy, eslint]
    - unit_test: {parallel: true, coverage_threshold: 80%}
    - integration_test: {services: [postgres, redis, kafka]}
    
  on_pr:
    - lint
    - unit_test
    - integration_test
    - contract_test: {schema_compatibility: true}
    - e2e_smoke: {journeys: CRITICAL_JOURNEYS[:2]}
    
  on_merge_to_main:
    - full_e2e: {journeys: ALL, browsers: [chromium, firefox]}
    - performance_test: {max_p95_latency: 500ms}
    - security_scan: [trivy, bandit, npm-audit]

# 测试数据管理
test_data:
  fixtures:
    - 预置10场世界杯比赛赔率时间序列
    - 预置50个事件记录（不同类型、严重度）
    - 预置已知关联（用于关联引擎准确率验证）
  anonymization: 所有测试数据不得包含真实用户信息
```


## 十五、数据治理与留存

### 15.1 数据生命周期

```
数据生命周期管理:

  采集 ──▶ 热存储 ──▶ 温存储 ──▶ 冷存储 ──▶ 删除
  (Kafka)  (Timescale) (S3/OSS)  (Glacier)  (合规)

  各阶段:
  - 热存储 (0-30天): TimescaleDB, 全量索引, 实时查询
  - 温存储 (30天-1年): TimescaleDB 压缩分块 + S3 Parquet
  - 冷存储 (1-5年): S3 Glacier Deep Archive, 仅批量恢复
  - 删除 (>5年): 按合规策略执行
```

### 15.2 数据留存策略

| 数据类型 | 热存储 | 温存储 | 冷存储 | 说明 |
|---|---|---|---|---|
| 赔率Tick数据 | 30天 | 1年 | 5年 | 高频数据，存储成本高 |
| 事件记录 | 90天 | 2年 | 10年 | 事件分析长期价值 |
| 关联分析结果 | 180天 | 永久 | — | 分析结果体积小，永久保留 |
| 用户行为日志 | 30天 | 1年 | — | 按GDPR可请求删除 |
| 聚合统计数据 | 永久 | — | — | 预计算聚合，体积可控 |
| 原始消息(Kafka) | 7天 | — | — | 仅用于回放和恢复 |

### 15.3 TimescaleDB分区策略

```sql
-- 按时间分区 (Hypertable)
SELECT create_hypertable('odds_records', 'timestamp', 
    chunk_time_interval => INTERVAL '1 day');

-- 压缩策略 (7天后压缩为列式存储)
ALTER TABLE odds_records SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'provider, match_id',
    timescaledb.compress_orderby = 'timestamp DESC, bookmaker, market'
);
SELECT add_compression_policy('odds_records', INTERVAL '7 days');

-- 数据保留策略
SELECT add_retention_policy('odds_records', INTERVAL '365 days');

-- 连续聚合 (预计算小时级OHLC)
CREATE MATERIALIZED VIEW odds_hourly_ohlc
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', timestamp) AS bucket,
    match_id, bookmaker, market, selection,
    FIRST(odds_value, timestamp) as open,
    MAX(odds_value) as high,
    MIN(odds_value) as low,
    LAST(odds_value, timestamp) as close,
    AVG(odds_value) as mean,
    COUNT(*) as tick_count
FROM odds_records
GROUP BY bucket, match_id, bookmaker, market, selection;
```

### 15.4 合规考虑

| 法规 | 适用范围 | 系统措施 |
|---|---|---|
| **GDPR** | 欧盟用户 | 数据导出/删除API, 用户同意管理, 数据最小化 |
| **CCPA** | 加州用户 | 个人信息披露, 选择退出机制 |
| **数据本地化** | 特定国家 | 支持按地域路由数据至对应区域的存储 |
| **审计追踪** | 全部 | 所有数据变更记录不可变审计日志 |


## 十六、部署架构与CI/CD

### 16.1 Kubernetes部署拓扑

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                                 │
│                                                                      │
│  ┌─────────────────────┐  ┌─────────────────────┐                   │
│  │   Ingress NGINX     │  │   cert-manager       │                   │
│  │   (TLS Termination) │  │   (Auto TLS)         │                   │
│  └─────────┬───────────┘  └─────────────────────┘                   │
│            │                                                         │
│  ┌─────────▼───────────────────────────────────────────────────┐    │
│  │                    Service Mesh (Istio)                       │    │
│  │   mTLS │ 流量管理 │ 故障注入 │ 可观测性                       │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    应用层 (Deployments)                       │    │
│  │                                                               │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │    │
│  │  │ Frontend │ │GraphQL   │ │Analytics │ │Pipeline  │        │    │
│  │  │ (Nginx)  │ │ Server   │ │ Engine   │ │ Workers  │        │    │
│  │  │ replicas │ │ replicas │ │ replicas │ │ replicas │        │    │
│  │  │ : 2      │ │ : 3      │ │ : 2      │ │ : 3      │        │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │    │
│  │                                                               │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │    │
│  │  │Data Svc  │ │Adapter   │ │Adapter   │ │Notifier  │        │    │
│  │  │ replicas │ │Odds Mgr  │ │Event Mgr │ │ Service  │        │    │
│  │  │ : 2      │ │ : 2      │ │ : 2      │ │ : 1      │        │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    数据层 (StatefulSets)                      │    │
│  │                                                               │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │    │
│  │  │Timescale │ │ Redis    │ │ Kafka    │ │ MinIO    │        │    │
│  │  │(3-node)  │ │(Sentinel)│ │(3-node)  │ │(4-node)  │        │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### 16.2 环境策略

| 环境 | 用途 | 数据 | 部署方式 |
|---|---|---|---|
| `dev` | 本地开发 | Mock数据 + SQLite/嵌入式 | Docker Compose |
| `staging` | 集成测试 | 脱敏生产数据子集 | K8s (单节点) |
| `production` | 生产环境 | 全量 | K8s (多节点, 多AZ) |
| `sandbox` | 数据源接入测试 | 隔离数据 | K8s (按需创建/销毁) |

### 16.3 CI/CD管道

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CI/CD Pipeline                               │
│                                                                      │
│  PR Open                                                             │
│    │                                                                 │
│    ▼                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │  Lint    │───▶│  Test    │───▶│  Build   │───▶│  Deploy  │       │
│  │  (2min)  │    │  (5min)  │    │  (3min)  │    │  Preview │       │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘       │
│                                                                      │
│  Merge to Main                                                       │
│    │                                                                 │
│    ▼                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │  Test    │───▶│  Build   │───▶│  Deploy  │───▶│  Smoke   │       │
│  │  (Full)  │    │  Image   │    │  Staging │    │  Test    │       │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘       │
│                                                       │              │
│                                                       ▼              │
│                                              ┌──────────────┐       │
│                                              │  Deploy Prod  │       │
│                                              │  (Canary 10%  │       │
│                                              │   → 100%)     │       │
│                                              └──────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

### 16.4 部署策略

```yaml
# 金丝雀部署配置 (Istio VirtualService)
canary_deployment:
  stages:
    - weight: 5%
      duration: 10m
      metrics_check:
        - error_rate < 1%
        - p95_latency < baseline * 1.2
    - weight: 25%
      duration: 30m
    - weight: 100%
      duration: permanent
  
  auto_rollback:
    condition: error_rate > 5% OR p95_latency > baseline * 2
    action: revert_to_previous_version

# 数据库迁移策略
database_migration:
  strategy: expand-contract  # 零停机
  steps:
    1. expand:  ADD COLUMN (nullable) - 向后兼容
    2. migrate: 后台填充数据
    3. contract: DROP old_column (确认无引用后)
  
  rollback:
    - 每步可独立回滚
    - 禁止在事务中混合DDL和DML
```

### 16.5 基础设施即代码

| 组件 | 工具 | 说明 |
|---|---|---|
| K8s资源配置 | Helm Charts + Kustomize | 分层配置（base → env overlay） |
| 云基础设施 | Terraform / Pulumi | 网络、存储、K8s集群 |
| 密钥管理 | Vault + External Secrets | K8s Secrets同步 |
| 镜像仓库 | Harbor / ECR | 漏洞扫描 + 签名验证 |
| GitOps | ArgoCD | 声明式部署，自动同步 |


## 十七、API设计详案

### 17.1 GraphQL Schema

```graphql
# === 核心查询 ===

type Query {
  # 赔率查询
  oddsTimeline(
    input: OddsTimelineInput!
  ): OddsTimelineResponse!
  
  # 事件查询
  events(
    input: EventQueryInput!
  ): EventQueryResponse!
  
  # 关联查询
  correlations(
    input: CorrelationQueryInput!
  ): CorrelationQueryResponse!
  
  # 曲线管理
  curveDefinitions: [CurveDefinition!]!
  curveDefinition(id: ID!): CurveDefinition
  
  # 数据源状态
  dataSourceStatus: [DataSourceInfo!]!
  
  # 分析
  valueBets(
    matchIds: [ID!]!
    threshold: Float = 0.05
  ): [ValueBet!]!
  
  simulation(
    bracket: String!
    simulations: Int = 10000
  ): SimulationResult!
}

# === 核心类型 ===

type OddsTimelineResponse {
  curveId: ID!
  matchId: ID!
  dataPoints: [OddsPoint!]!
  seriesInfo: SeriesInfo!
  annotations: [EventAnnotation!]!  # 已标注的事件
  cursor: String  # 分页游标
}

type OddsPoint {
  timestamp: DateTime!
  value: Float!
  impliedProbability: Float
  volume: Float
  bookmaker: String!
  market: MarketType!
  selection: String!
}

type EventAnnotation {
  eventId: ID!
  eventType: String!
  title: String!
  severity: EventSeverity!
  timestamp: DateTime!
  relatedCurvePoint: OddsPoint  # 曲线上的对应点
  correlationScore: Float
  lagSeconds: Int
}

input OddsTimelineInput {
  matchId: ID!
  timeRange: TimeRangeInput!
  curves: [CurveConfigInput!]!
  granularity: Granularity = AUTO  # raw, 1min, 5min, 1hour
  includeAnnotations: Boolean = true
  maxPoints: Int = 10000
}

input CurveConfigInput {
  provider: String!
  bookmaker: String
  market: MarketType!
  selection: String
  calculation: String  # 衍生指标公式
}

# === 订阅 (实时推送) ===

type Subscription {
  oddsUpdated(matchIds: [ID!]!): OddsPoint!
  eventDetected(filters: EventFilterInput): EventRecord!
  correlationDetected(minScore: Float = 0.5): EventOddsCorrelation!
  anomalyAlert: AnomalyAlert!
}

# === 变更 ===

type Mutation {
  # 数据源管理
  enableDataSource(id: ID!): DataSourceInfo!
  disableDataSource(id: ID!): DataSourceInfo!
  updateDataSourceConfig(id: ID!, config: JSON!): DataSourceInfo!
  
  # 曲线管理
  createCurveDefinition(input: CurveDefinitionInput!): CurveDefinition!
  deleteCurveDefinition(id: ID!): Boolean!
  
  # 手动关联
  createManualCorrelation(input: ManualCorrelationInput!): EventOddsCorrelation!
  deleteCorrelation(id: ID!): Boolean!
  
  # 导出
  exportData(input: ExportInput!): ExportJob!
}
```

### 17.2 REST API (辅助)

```yaml
# REST API 用于不适合GraphQL的场景 (文件上传、批量导出)
rest_endpoints:
  health:
    GET /health: 健康检查
    GET /health/ready: 就绪检查
    GET /health/live: 存活检查
  
  data_ingest:
    POST /api/v1/ingest/odds: 批量写入赔率 (内部服务)
    POST /api/v1/ingest/events: 批量写入事件 (内部服务)
  
  export:
    POST /api/v1/export/csv: 导出CSV
    POST /api/v1/export/parquet: 导出Parquet
    GET /api/v1/export/{job_id}: 查询导出状态
  
  admin:
    GET /api/v1/admin/metrics: Prometheus metrics
    GET /api/v1/admin/ping: 连通性检查
    POST /api/v1/admin/cache/invalidate: 缓存失效
  
  webhook:
    POST /api/v1/webhook/odds/{provider}: 数据源回调接收
    POST /api/v1/webhook/events/{provider}: 事件回调接收
```

### 17.3 API版本化策略

```
版本化方案:
  - GraphQL: Schema演进 (添加字段不破坏兼容性, 废弃字段用 @deprecated)
  - REST: URL前缀版本 /api/v1/, /api/v2/
  
兼容性承诺:
  - 主版本间至少6个月重叠期
  - 废弃字段标注后至少保留3个月
  - 破坏性变更需提前通过changelog和邮件通知

速率限制响应头:
  X-RateLimit-Limit: 100
  X-RateLimit-Remaining: 67
  X-RateLimit-Reset: 1687538400
  Retry-After: 30
```


## 十八、数据库详细设计

### 18.1 核心表结构

```sql
-- ============================================
-- 赔率数据表 (时序主表)
-- ============================================
CREATE TABLE odds_records (
    id              UUID DEFAULT gen_random_uuid(),
    provider        VARCHAR(64) NOT NULL,
    source_id       VARCHAR(256) NOT NULL,       -- 数据源原始ID
    match_id        VARCHAR(128) NOT NULL,
    bookmaker       VARCHAR(128) NOT NULL,
    market          VARCHAR(32) NOT NULL,         -- h2h, over_under, asian_handicap, etc.
    selection       VARCHAR(64) NOT NULL,         -- home, away, draw, over, under
    odds_value      DOUBLE PRECISION NOT NULL,
    odds_format     VARCHAR(16) NOT NULL DEFAULT 'decimal',
    implied_prob    DOUBLE PRECISION,
    volume          DOUBLE PRECISION,
    
    -- 时间维度
    timestamp       TIMESTAMPTZ NOT NULL,         -- 数据源时间戳
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- 系统接收时间
    
    -- 扩展
    metadata        JSONB,
    
    -- 去重约束
    UNIQUE (provider, source_id)
);

-- 转换为Hypertable
SELECT create_hypertable('odds_records', 'timestamp');

-- 索引
CREATE INDEX idx_odds_match_ts ON odds_records (match_id, timestamp DESC);
CREATE INDEX idx_odds_provider_match ON odds_records (provider, match_id);
CREATE INDEX idx_odds_bookmaker ON odds_records (bookmaker, timestamp DESC);
CREATE INDEX idx_odds_market ON odds_records (market, timestamp DESC);

-- ============================================
-- 事件表
-- ============================================
CREATE TABLE events (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    provider        VARCHAR(64) NOT NULL,
    source_id       VARCHAR(256) NOT NULL,
    event_type      VARCHAR(64) NOT NULL,         -- injury, transfer, goal, red_card, etc.
    title           VARCHAR(512) NOT NULL,
    description     TEXT,
    timestamp       TIMESTAMPTZ NOT NULL,         -- 事件发生时间
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    severity        SMALLINT NOT NULL DEFAULT 1,  -- 1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL
    confidence      REAL NOT NULL DEFAULT 1.0,
    source_url      TEXT,
    
    -- 关联实体 (GIN索引支持JSON查询)
    entities        JSONB NOT NULL DEFAULT '[]',
    -- 例: [{"type": "team", "id": "england", "name": "英格兰"},
    --      {"type": "player", "id": "mbappe", "name": "Kylian Mbappé"}]
    
    -- 扩展
    metadata        JSONB,
    
    UNIQUE (provider, source_id)
);

CREATE INDEX idx_events_ts ON events (timestamp DESC);
CREATE INDEX idx_events_type ON events (event_type, timestamp DESC);
CREATE INDEX idx_events_entities ON events USING GIN (entities jsonb_path_ops);
CREATE INDEX idx_events_severity ON events (severity, timestamp DESC);

-- ============================================
-- 曲线定义表
-- ============================================
CREATE TABLE curve_definitions (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID,                          -- NULL = 系统级曲线
    name            VARCHAR(256) NOT NULL,
    description     TEXT,
    type            VARCHAR(32) NOT NULL,           -- odds, spread, volatility, derived
    source_config   JSONB NOT NULL,                 -- 数据源+筛选条件
    calculation     TEXT,                           -- 衍生指标公式 (仅 derived 类型)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (user_id, name)
);

-- ============================================
-- 关联记录表
-- ============================================
CREATE TABLE event_odds_correlations (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    event_id        UUID NOT NULL REFERENCES events(id),
    odds_id         UUID NOT NULL,
    curve_id        UUID NOT NULL REFERENCES curve_definitions(id),
    timestamp       TIMESTAMPTZ NOT NULL,          -- 关联时间点
    correlation_score REAL NOT NULL,               -- 0-1
    lag_seconds     INTEGER,                       -- 事件→赔率变动的延迟
    magnitude       REAL,                          -- 赔率变动幅度
    direction       VARCHAR(8),                    -- up, down, neutral
    detection_method VARCHAR(32) NOT NULL,         -- manual, changepoint, event_window, ml
    confidence      REAL NOT NULL DEFAULT 0.0,
    metadata        JSONB,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(64)                    -- 'system' or user_id
);

CREATE INDEX idx_corr_event ON event_odds_correlations (event_id);
CREATE INDEX idx_corr_curve ON event_odds_correlations (curve_id);
CREATE INDEX idx_corr_score ON event_odds_correlations (correlation_score DESC);
CREATE INDEX idx_corr_ts ON event_odds_correlations (timestamp DESC);

-- ============================================
-- 数据源状态表
-- ============================================
CREATE TABLE data_source_status (
    provider_id     VARCHAR(64) PRIMARY KEY,
    provider_type   VARCHAR(16) NOT NULL,          -- odds, event
    name            VARCHAR(128) NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    priority        SMALLINT NOT NULL DEFAULT 10,
    config          JSONB NOT NULL DEFAULT '{}',
    health_status   VARCHAR(16) NOT NULL DEFAULT 'unknown',  -- healthy, degraded, unhealthy
    last_sync_at    TIMESTAMPTZ,
    last_error      TEXT,
    error_count     INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms  REAL,
    rate_limit_remaining INTEGER,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================
-- 用户行为日志表 (审计)
-- ============================================
CREATE TABLE audit_log (
    id              UUID DEFAULT gen_random_uuid(),
    user_id         UUID,
    action          VARCHAR(64) NOT NULL,          -- query, export, config_change, login
    resource_type   VARCHAR(64),                   -- odds_records, curve_definition, etc.
    resource_id     UUID,
    details         JSONB,
    ip_address      INET,
    user_agent      TEXT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('audit_log', 'timestamp');
SELECT add_retention_policy('audit_log', INTERVAL '2 years');
```

### 18.2 读写分离与缓存策略

```
读写分离架构:

  写请求 ──▶ Primary (TimescaleDB) ──▶ 流复制 ──▶ Replica 1 (只读)
                                                    │
                                                    ├──▶ Replica 2 (只读)
                                                    │
                                                    └──▶ Replica 3 (只读, 分析专用)

  读请求 ──▶ PgBouncer (连接池) ──▶ 负载均衡 ──▶ Replica 1/2

缓存策略 (Redis):

  热点数据缓存:
  - 最近24小时的赔率tick数据: TTL 60s (高变化率)
  - 历史聚合数据 (>24h): TTL 1h (低变化率)
  - 数据源状态: TTL 30s
  - 曲线定义: TTL 5min
  - 关联结果: TTL 10min
  
  缓存失效:
  - 写穿透 (Write-Through): 写入时同步更新缓存
  - 主动失效: 数据管道完成批次后发送失效事件
  - 惰性过期: TTL + 访问时检查
```


## 十九、事件类型与赔率市场分类学

### 19.1 事件类型分类体系

```
事件分类体系 (三层):

Level 1: 域
├── 赛场事件 (Match Events)
│   ├── 进球 (goal)
│   │   ├── 常规进球 (regular_goal)
│   │   ├── 点球进球 (penalty_goal)
│   │   ├── 乌龙球 (own_goal)
│   │   └── 绝杀进球 (last_minute_goal)
│   ├── 纪律事件 (discipline)
│   │   ├── 黄牌 (yellow_card)
│   │   ├── 红牌 (red_card)
│   │   └── 两黄变红 (second_yellow)
│   ├── 换人 (substitution)
│   │   ├── 战术换人 (tactical_sub)
│   │   └── 伤停换人 (injury_sub)
│   ├── 判罚 (decision)
│   │   ├── 点球判罚 (penalty_awarded)
│   │   ├── VAR干预 (var_intervention)
│   │   └── 越位 (offside)
│   └── 比赛阶段 (match_phase)
│       ├── 开球 (kickoff)
│       ├── 半场 (halftime)
│       ├── 伤停补时 (injury_time)
│       └── 全场结束 (fulltime)
│
├── 人员事件 (Personnel Events)
│   ├── 伤病 (injury)
│   │   ├── 训练受伤 (training_injury)
│   │   ├── 比赛受伤 (match_injury)
│   │   └── 复出 (return_from_injury)
│   ├── 转会 (transfer)
│   │   ├── 转会传闻 (transfer_rumor)
│   │   ├── 确认转会 (transfer_confirmed)
│   │   └── 租借 (loan)
│   ├── 合同 (contract)
│   │   ├── 续约 (contract_extension)
│   │   └── 到期 (contract_expiry)
│   └── 状态 (status)
│       ├── 停赛 (suspension)
│       └── 退役 (retirement)
│
├── 管理事件 (Management Events)
│   ├── 教练变更 (manager_change)
│   │   ├── 解雇 (sacked)
│   │   └── 新任 (appointed)
│   ├── 所有权变更 (ownership_change)
│   └── 战术公告 (tactical_announcement)
│       ├── 首发阵容 (starting_xi_announced)
│       └── 阵型变更 (formation_change)
│
├── 外部事件 (External Events)
│   ├── 天气 (weather)
│   │   ├── 极端天气 (extreme_weather)
│   │   └── 场地状况 (pitch_condition)
│   ├── 政治/社会 (political)
│   │   ├── 赛事抵制 (boycott)
│   │   └── 安全事件 (security_incident)
│   └── 市场 (market)
│       ├── 大额投注 (large_wager)
│       └── 市场暂停 (market_suspension)
│
└── 媒体事件 (Media Events)
    ├── 新闻发布会 (press_conference)
    ├── 社交媒体 (social_media)
    │   ├── 球员推文 (player_tweet)
    │   └── 官方公告 (official_announcement)
    └── 谣言 (rumor)
```

### 19.2 事件影响模型

```python
class EventImpactProfile:
    """事件对赔率的影响特征"""
    
    # 每种事件类型的典型影响参数
    IMPACT_PROFILES = {
        "goal": {
            "immediacy": "instant",        # 即刻反应
            "typical_lag": (2, 15),        # 秒
            "magnitude_range": (0.05, 0.60),  # 赔率变动幅度
            "duration": (60, 300),         # 影响持续秒数
            "direction": "situational",    # 取决于哪队进球
            "decay_pattern": "sharp_then_stable",  # 剧烈→平稳
        },
        "red_card": {
            "immediacy": "instant",
            "typical_lag": (5, 30),
            "magnitude_range": (0.10, 0.80),
            "duration": (600, 3600),
            "direction": "against_team",
            "decay_pattern": "step_change",     # 阶梯式变化
        },
        "injury_announcement": {
            "immediacy": "gradual",
            "typical_lag": (30, 300),
            "magnitude_range": (0.02, 0.30),
            "duration": (1800, 86400),
            "direction": "against_team",
            "decay_pattern": "gradual_absorption",  # 逐步消化
        },
        "starting_xi_announced": {
            "immediacy": "near_instant",
            "typical_lag": (10, 120),
            "magnitude_range": (0.01, 0.15),
            "duration": (600, 7200),
            "direction": "situational",
            "decay_pattern": "pre_match_adjustment",
        },
        "transfer_rumor": {
            "immediacy": "delayed",
            "typical_lag": (60, 3600),
            "magnitude_range": (0.005, 0.05),
            "duration": (3600, 86400),
            "direction": "situational",
            "decay_pattern": "slow_absorption",
        },
        "weather_extreme": {
            "immediacy": "gradual",
            "typical_lag": (60, 600),
            "magnitude_range": (0.01, 0.10),
            "duration": (1800, 14400),
            "direction": "toward_under",
            "decay_pattern": "pre_match_plateau",
        },
    }
```

### 19.3 赔率市场类型目录

| 市场类型 | 代码 | 说明 | 典型选项 | 数据源支持度 |
|---|---|---|---|---|
| **1X2 (胜平负)** | `h2h` | 比赛结果 | home, draw, away | ⭐⭐⭐⭐⭐ |
| **亚洲盘 (AH)** | `asian_handicap` | 含让球的胜负 | home_line, away_line | ⭐⭐⭐⭐⭐ |
| **大小球 (OU)** | `over_under` | 总进球数 | over_N, under_N | ⭐⭐⭐⭐⭐ |
| **正确比分** | `correct_score` | 精确比分 | 0-0, 1-0, 1-1, ... | ⭐⭐⭐⭐ |
| **半全场** | `ht_ft` | 半场/全场组合 | H/H, H/D, H/A, ... | ⭐⭐⭐ |
| **双方进球** | `btts` | 两队都进球 | yes, no | ⭐⭐⭐⭐ |
| **最先/最后进球** | `first_last_goal` | 进球顺序 | team_a, team_b, no_goal | ⭐⭐⭐ |
| **总角球** | `corners_total` | 角球总数 | over_N, under_N | ⭐⭐⭐ |
| **总黄牌** | `cards_total` | 黄牌总数 | over_N, under_N | ⭐⭐⭐ |
| **晋级盘** | `to_qualify` | 淘汰赛晋级 | team_a, team_b | ⭐⭐⭐ |
| **夺冠盘** | `outright` | 赛事冠军 | 各队 | ⭐⭐⭐⭐ |
| **金靴奖** | `top_scorer` | 最佳射手 | 各球员 | ⭐⭐⭐ |
| **点球判罚** | `penalty_awarded` | 是否有点球 | yes, no | ⭐⭐ |
| **红牌判罚** | `red_card_awarded` | 是否有红牌 | yes, no | ⭐⭐ |


## 二十、通知与预警系统

### 20.1 通知架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                       通知系统架构                                    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                      事件源                                   │    │
│  │  关联引擎  │  异常检测  │  数据源状态  │  系统告警  │  日程   │    │
│  └───────────────────────┬──────────────────────────────────────┘    │
│                          │                                           │
│                          ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                   通知分发器 (Notification Dispatcher)         │    │
│  │                                                                   │
│  │  优先级队列 ──▶ 去重 ──▶ 路由 ──▶ 模板渲染 ──▶ 渠道适配       │    │
│  └───────────────────────┬──────────────────────────────────────┘    │
│                          │                                           │
│          ┌───────────────┼───────────────┬───────────────┐          │
│          ▼               ▼               ▼               ▼          │
│     ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐        │
│     │ Web    │     │ Email  │     │ Slack/ │     │Webhook │        │
│     │ Push   │     │        │     │Teams   │     │(自定义) │        │
│     └────────┘     └────────┘     └────────┘     └────────┘        │
└──────────────────────────────────────────────────────────────────────┘
```

### 20.2 预警规则引擎

```python
class AlertRule:
    """用户可配置的预警规则"""
    id: str
    user_id: str
    name: str
    enabled: bool = True
    
    # 触发条件 (组合逻辑)
    conditions: List[Condition]
    logic: str = "AND"  # AND / OR
    
    # 作用范围
    scope: AlertScope
    
    # 通知配置
    channels: List[str]  # ["web", "email", "slack"]
    cooldown_seconds: int = 300  # 同一规则告警冷却期
    
    # 时间段限制
    active_hours: Optional[str]  # cron表达式

class AlertScope:
    match_ids: Optional[List[str]]
    bookmakers: Optional[List[str]]
    markets: Optional[List[str]]
    event_types: Optional[List[str]]

class Condition:
    metric: str       # odds_change, correlation_score, volume_spike
    operator: str     # gt, lt, gte, lte, eq, change_pct
    threshold: float
    window_seconds: int = 60
```

**预置预警规则模板:**

| 规则名称 | 触发条件 | 适用场景 |
|---|---|---|
| **异常赔率变动** | 任意博彩公司赔率变动 >15% (60s窗口) | 检测重大事件影响 |
| **关联强度告警** | 新检测到关联强度 >0.8 的事件-赔率对 | 高影响力事件通知 |
| **数据源中断** | 数据源超过120s无数据推送 | 运维告警 |
| **价值投注发现** | 隐含概率偏差 >5% | 投注机会提示 |
| **多博彩公司分歧** | 3+博彩公司赔率标准差 > 均值10% | 市场不确定性 |
| **成交量异常** | 单场比赛成交量 > 历史均值3σ | 异常博彩活动 |

### 20.3 实时推送 (WebSocket/SSE)

```python
# WebSocket 通道设计
class RealtimeChannel:
    """
    频道设计:
    - /ws/odds/{match_id}           → 单场比赛赔率实时推送
    - /ws/events/{match_id}         → 单场比赛事件推送
    - /ws/dashboard                 → 用户面板聚合推送
    - /ws/alerts/{user_id}          → 个人告警推送
    """
    
    async def handle_odds_channel(self, websocket, match_id: str):
        """赔率实时推送"""
        async for odds_tick in self.odds_stream.subscribe(match_id):
            await websocket.send_json({
                "type": "odds_update",
                "match_id": match_id,
                "data": odds_tick.dict(),
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def handle_dashboard_channel(self, websocket, user_id: str):
        """聚合面板推送 (节流合并)"""
        async for batch in self.aggregator.subscribe(user_id):
            await websocket.send_json({
                "type": "dashboard_update",
                "curves": batch.curve_updates,    # 多个曲线的增量更新
                "new_events": batch.new_events,
                "alerts": batch.active_alerts,
            })
```

### 20.4 通知优先级矩阵

| 优先级 | 类型 | 渠道 | 示例 |
|---|---|---|---|
| **P0 - 紧急** | 系统级故障 | 电话 + Slack + Email | 数据库不可用, Kafka集群宕机 |
| **P1 - 严重** | 数据源中断 | Slack + Email | API数据源超时, 管道积压 >5min |
| **P2 - 警告** | 业务异常 | Slack + Web | 异常赔率变动, 关联强度 >0.9 |
| **P3 - 信息** | 用户通知 | Web + Email(摘要) | 价值投注发现, 日报生成 |
| **P4 - 调试** | 系统日志 | 仅日志 | 缓存命中率变化, GC停顿 |


## 二十一、系统容量规划

### 21.1 数据量估算

```
假设场景: 2026世界杯 (64场比赛)

赔率数据:
  - 每场比赛50+博彩公司
  - 每博彩公司20+市场类型
  - 每市场每30秒更新一次 (滚球期间可达5秒)
  - 赛前72小时 + 比赛中90分钟
  
  估算:
  - 单场比赛: 50 × 20 × (72h×120 + 1.5h×720) = 50 × 20 × 9720 ≈ 9.7M ticks
  - 64场比赛: 64 × 9.7M ≈ 620M ticks
  - 考虑其他联赛: 年数据量约 50-100亿 ticks

事件数据:
  - 每场比赛50-200个事件
  - 64场比赛: ~10K 赛场事件
  - 场外事件 (伤病/转会/新闻): ~50K/月
  - 全球新闻 (GDELT): ~100K/天 (过滤后 ~5K 相关)

存储估算 (年):
  - 赔率tick: 100亿 × 150 bytes ≈ 1.5TB (原始) → 300GB (压缩后)
  - 事件: 200万 × 2KB ≈ 4GB
  - 关联记录: 500万 × 1KB ≈ 5GB
  - 用户日志: 取决于用户量
  - 总计: ~500GB/年 (含索引和冗余)
```

### 21.2 性能SLO

| 指标 | 目标 | 测量方式 |
|---|---|---|
| **可用性** | 99.9% (月停机 <43min) | 健康检查探针 |
| **API P95延迟** | < 200ms (读), < 500ms (写) | Prometheus histogram |
| **数据新鲜度** | < 5s (实时数据源), < 1h (批量数据源) | last_sync_at 监控 |
| **关联检测延迟** | < 30s (事件发生后到关联结果可用) | 管道端到端追踪 |
| **图表渲染** | < 2s (10000数据点, 5条曲线) | 前端性能监控 |
| **并发用户** | 支持500并发用户, P95延迟不劣化 >50% | k6负载测试 |

### 21.3 扩展策略

```yaml
horizontal_scaling:
  stateless_services:
    - GraphQL Server: HPA (CPU 70%)
    - Analytics Engine: HPA (CPU 60% + custom: queue_depth)
    - Pipeline Workers: KEDA (Kafka lag)
    - Adapter Managers: 固定副本 (每数据源类型1-2个)

  stateful_services:
    - TimescaleDB: 
        - 读扩展: 增加只读副本 (最多5个)
        - 写扩展: 按match_id分片 (如需要)
    - Kafka: 增加分区数 (预估: 32分区/topic)
    - Redis: Redis Cluster (3主3从)

  cost_optimization:
    - 非赛事期间缩减至最小副本
    - Spot实例用于批处理任务
    - 压缩策略自动降低存储成本
```


## 二十二、术语表

| 术语 | 英文 | 定义 |
|---|---|---|
| 赔率 | Odds | 博彩公司为特定结果提供的赔付倍数 |
| 隐含概率 | Implied Probability | 从赔率反推的事件发生概率 (= 1/Decimal Odds) |
| 赔率曲线 | Odds Curve / Timeline | 赔率随时间变化的序列 |
| 事件 | Event | 可能影响赔率的外部信息（进球、伤病等） |
| 关联 | Correlation | 事件与赔率变动之间的统计学关系 |
| 变点 | Changepoint | 时间序列中统计特性发生突变的点 |
| 滞后 | Lag | 事件发生到赔率反应的时间间隔 |
| 博彩公司 | Bookmaker | 提供赔率数据的博彩运营商 |
| 市场 | Market | 投注类型（胜平负、大小球、亚洲盘等） |
| 数据源 | Data Source / Provider | 提供赔率或事件数据的上游服务 |
| 适配器 | Adapter | 将异构数据源封装为统一接口的组件 |
| 管道 | Pipeline | 数据从采集到存储的处理链路 |
| 价值投注 | Value Bet | 隐含概率低于真实概率的投注机会 |
| 蒙特卡洛模拟 | Monte Carlo Simulation | 通过大量随机抽样估计概率分布的方法 |


> **💡 简历价值、AI扩展方案和面试策略请参考单独文档**: [ProjectResumeGuide.MD](ProjectResumeGuide.MD)


