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