# 前端校准状态面板 — 实施计划

## Context

四个自校准方案（A-D）已全部实现并在服务器上运行，当前没有任何可视化手段查看它们的运行状态、结果和健康情况。需要一个前端面板展示每种方案的运行状态，便于监控和排查问题。

---

## Step 1：Backend — `PollingController` 添加校准任务状态追踪

**文件**: `backend/scheduler/scheduler.py`

当前 `PollingController.__init__` 中已注册三个校准相关定时任务，但是没有任何字段记录它们的执行结果。

### 1.1 添加状态追踪字段

在 `__init__` 的 `self.mode = "auto"` 附近添加：

```python
# 校准任务状态追踪
self.last_outcome_check_at: str | None = None
self.last_outcome_check_stats: dict | None = None
self.last_auto_tune_at: str | None = None
self.last_auto_tune_adjustments: list[str] | None = None
self.last_full_calibration_at: str | None = None
self.last_full_calibration_f1_old: float | None = None
self.last_full_calibration_f1_new: float | None = None
```

### 1.2 在回调方法中记录状态

`scheduled_outcome_check` 执行后记录：
- `self.last_outcome_check_at = utc_now_iso()`
- `self.last_outcome_check_stats = stats`

`scheduled_auto_tune` 执行后记录：
- `self.last_auto_tune_at = utc_now_iso()`
- `self.last_auto_tune_adjustments = result.get("adjusted_keys")`

`scheduled_full_calibration` 执行后记录：
- `self.last_full_calibration_at = utc_now_iso()`
- `self.last_full_calibration_f1_old = result.get("old_f1")`
- `self.last_full_calibration_f1_new = result.get("new_f1")`

### 1.3 在 `get_status()` 中添加校准状态字段

```python
def get_status(self) -> dict:
    return {
        # ... 现有字段 ...
        "calibration": {
            "outcome_check": {
                "last_run_at": self.last_outcome_check_at,
                "stats": self.last_outcome_check_stats,
            },
            "auto_tune": {
                "last_run_at": self.last_auto_tune_at,
                "last_adjustments": self.last_auto_tune_adjustments,
            },
            "full_calibration": {
                "last_run_at": self.last_full_calibration_at,
                "f1_old": self.last_full_calibration_f1_old,
                "f1_new": self.last_full_calibration_f1_new,
            },
        },
    }
```

---

## Step 2：Backend — 新建 `/api/v1/calibration/status` 端点

**文件**: `backend/api/routes.py`

新增一个独立端点，返回四个方案的完整状态。不从 Dashboard 接口返回以避免耦合。

```python
@router.get("/calibration/status")
async def get_calibration_status(request: Request) -> dict[str, Any]:
    """返回四个自校准方案的运行状态"""
    database = get_database(request)
    controller = get_controller(request)
    status = controller.get_status()
    cal = status.get("calibration", {})

    # 方案 A：从数据库获取命中率 + 待评估数
    from datetime import datetime, timedelta, timezone
    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    signal_types = ["surge", "dump", "rank_surge", "rank_dump", "combined_surge", "combined_dump", "wr_surge", "wr_dump"]
    hit_rates = {}
    for st in signal_types:
        hr = database.get_hit_rate(st, since_24h)
        if hr is not None:
            hit_rates[st] = round(hr * 100, 1)
    pending = database.get_pending_outcomes(limit=0)  # count 模式
    # 用 count query 替代
    pending_count = database.count_pending_outcomes()

    return _api_ok({
        "approach_a": {
            "name": "Outcome Tracking",
            "enabled": True,
            "status": "active",
            "last_check_at": cal.get("outcome_check", {}).get("last_run_at"),
            "stats": cal.get("outcome_check", {}).get("stats"),
            "hit_rates": hit_rates,
            "pending_evaluations": pending_count,
        },
        "approach_b": {
            "name": "Agent Adaptive Thresholds",
            "enabled": True,
            "status": "active",
            "description": "按 Agent 历史波动动态缩放信号阈值",
        },
        "approach_c": {
            "name": "Dynamic SNR Window",
            "enabled": True,
            "status": "active",
            "description": "按信噪比动态调整趋势检测窗口",
        },
        "approach_d": {
            "name": "Full Calibration",
            "enabled": True,
            "status": "active",
            "last_run_at": cal.get("full_calibration", {}).get("last_run_at"),
            "f1_old": cal.get("full_calibration", {}).get("f1_old"),
            "f1_new": cal.get("full_calibration", {}).get("f1_new"),
        },
        "auto_tune": {
            "last_run_at": cal.get("auto_tune", {}).get("last_run_at"),
            "last_adjustments": cal.get("auto_tune", {}).get("last_adjustments"),
        },
    })
```

### 2.1 添加 `count_pending_outcomes()` 方法

**文件**: `backend/db/database.py`

```python
def count_pending_outcomes(self) -> int:
    with self._connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM signal_outcomes WHERE evaluated_at IS NULL",
        ).fetchone()
    return row["cnt"] if row else 0
```

---

## Step 3：Frontend — 新增类型和 API 函数

**文件**: `frontend/web/src/api/client.ts`

### 3.1 新增接口

```typescript
export interface CalibrationApproachStatus {
  name: string
  enabled: boolean
  status: string
  last_run_at?: string | null
  stats?: { checked: number; correct: number; wrong: number; skipped: number } | null
  hit_rates?: Record<string, number> | null
  pending_evaluations?: number | null
  f1_old?: number | null
  f1_new?: number | null
  description?: string | null
}

export interface CalibrationStatus {
  approach_a: CalibrationApproachStatus
  approach_b: CalibrationApproachStatus
  approach_c: CalibrationApproachStatus
  approach_d: CalibrationApproachStatus
  auto_tune: {
    last_run_at: string | null
    last_adjustments: string[] | null
  }
}
```

### 3.2 新增 API 函数

```typescript
export async function fetchCalibrationStatus() {
  return apiGet<CalibrationStatus>('/calibration/status')
}
```

---

## Step 4：Frontend — Dashboard 新增校准状态面板

**文件**: `frontend/web/src/pages/Dashboard.tsx`

### 4.1 新增 import

```typescript
import { fetchCalibrationStatus, type CalibrationStatus } from '../api/client'
import { Activity, BarChart3, Target, Cpu, AlertTriangle, CheckCircle, Clock } from 'lucide-react'
```

### 4.2 新增 useQuery

```typescript
const { data: calStatus } = useQuery({
  queryKey: ['calibration-status'],
  queryFn: fetchCalibrationStatus,
  refetchInterval: 120_000,
})
```

### 4.3 在右侧面板中添加"Self-Calibration"区块

在 "Polling Status" 和 "Recent Events" 之间插入新面板：

```tsx
{/* Self-Calibration Status */}
<div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
  <h2 className="text-sm font-semibold mb-2 text-gray-400 uppercase tracking-wider">
    Self-Calibration
  </h2>
  {!calStatus ? (
    <div className="text-xs text-gray-500">Loading...</div>
  ) : (
    <div className="space-y-2">
      {/* 方案 A */}
      <CalibrationRow
        label="A: Outcome Tracking"
        status={calStatus.approach_a.status}
        badge={calStatus.approach_a.stats ? 
          `${calStatus.approach_a.stats.correct}/${calStatus.approach_a.stats.checked} correct` : 
          'pending'}
        lastRun={calStatus.approach_a.last_run_at}
        hitRate={calStatus.approach_a.hit_rates?.surge}
      />
      {/* 方案 B */}
      <CalibrationRow
        label="B: Adaptive Thresholds"
        status={calStatus.approach_b.status}
        badge="active"
      />
      {/* 方案 C */}
      <CalibrationRow
        label="C: Dynamic Window"
        status={calStatus.approach_c.status}
        badge="active"
      />
      {/* 方案 D */}
      <CalibrationRow
        label="D: Full Calibration"
        status={calStatus.approach_d.status}
        badge={calStatus.approach_d.f1_new != null ?
          `F1 ${calStatus.approach_d.f1_new?.toFixed(3)}` : 'pending'}
        lastRun={calStatus.approach_d.last_run_at}
        f1Old={calStatus.approach_d.f1_old}
        f1New={calStatus.approach_d.f1_new}
      />
    </div>
  )}
</div>
```

### 4.4 新增 CalibrationRow 子组件

```tsx
function CalibrationRow({
  label,
  status,
  badge,
  lastRun,
  hitRate,
  f1Old,
  f1New,
}: {
  label: string
  status: string
  badge?: string
  lastRun?: string | null
  hitRate?: number | null
  f1Old?: number | null
  f1New?: number | null
}) {
  return (
    <div className="text-xs border-b border-gray-800/50 last:border-0 pb-1.5 last:pb-0">
      <div className="flex items-center justify-between">
        <span className="text-gray-300">{label}</span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
          status === 'active' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-yellow-500/10 text-yellow-400'
        }`}>
          {badge || status}
        </span>
      </div>
      <div className="flex items-center gap-2 mt-0.5 text-gray-500">
        {lastRun && (
          <span className="flex items-center gap-1">
            <Clock size={10} />
            {new Date(lastRun).toLocaleTimeString()}
          </span>
        )}
        {hitRate != null && (
          <span className="text-gray-400">
            Surge hit: {hitRate}%
          </span>
        )}
        {f1Old != null && f1New != null && (
          <span className={f1New >= f1Old ? 'text-emerald-400' : 'text-red-400'}>
            F1: {f1Old.toFixed(3)} → {f1New.toFixed(3)}
          </span>
        )}
      </div>
    </div>
  )
}
```

---

## 文件变更清单

| 文件 | 操作 | 变更内容 |
|------|------|---------|
| `backend/scheduler/scheduler.py` | 修改 | 添加 6 个校准状态字段 + 3 处回调记录 + get_status() 增加 calibration 段 |
| `backend/db/database.py` | 修改 | 添加 `count_pending_outcomes()` 方法 |
| `backend/api/routes.py` | 修改 | 新增 `GET /calibration/status` 端点 |
| `frontend/web/src/api/client.ts` | 修改 | 新增 `CalibrationApproachStatus` / `CalibrationStatus` 接口 + `fetchCalibrationStatus()` |
| `frontend/web/src/pages/Dashboard.tsx` | 修改 | 新增 useQuery + 校准状态面板 + CalibrationRow 组件 |

---

## 验证

1. 启动后端：`cd backend && uvicorn main:app --reload --port 8000`
2. 访问 `http://localhost:8000/api/v1/calibration/status` 确认 JSON 返回
3. 启动前端：`cd frontend/web && npm run dev`
4. 观察 Dashboard 右侧新增的 Self-Calibration 面板，显示 4 行状态
5. 确认 `last_run_at` 为空（新 deployment 尚未运行过定时任务）不会导致前端报错
