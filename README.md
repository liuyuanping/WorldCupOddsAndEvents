# 赔率-事件关联分析系统

前后端分离的体育赔率-事件关联分析平台 MVP。

## 架构

```
frontend/ (port 5173)              backend/ (port 8000)
┌─────────────────────┐           ┌─────────────────────────┐
│ React + TypeScript   │───REST──▶│ FastAPI                  │
│ + ECharts + Zustand  │           │ + SQLAlchemy + SQLite    │
└─────────────────────┘           │ + CUSUM 关联引擎          │
                                  └─────────────────────────┘
```

## 快速启动

### 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn sqlalchemy pydantic pydantic-settings numpy scipy httpx aiosqlite python-dateutil
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs for Swagger API docs.

### 前端

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Docker Compose

```bash
docker-compose up
```

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /api/v1/odds` | 赔率数据查询 |
| `GET /api/v1/events` | 事件数据查询 |
| `GET /api/v1/correlations` | 关联分析 |
| `GET /api/v1/datasources` | 数据源管理 |
| `WS /ws/realtime` | 实时赔率推送 |

## 技术栈

- **前端**: React 19 + TypeScript + ECharts + Zustand + Vite
- **后端**: Python FastAPI + SQLAlchemy + SQLite
- **分析引擎**: CUSUM 变点检测 + 事件窗口分析 + 多方法融合评分
- **数据源**: 适配器模式 (Mock Odds + Mock Events)
