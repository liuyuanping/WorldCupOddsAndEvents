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