# 价格反转预警 — 实现清单

## 阶段一：数据层

- [ ] 1.1 db/models.py — 新增 PriceTick 数据类
- [ ] 1.2 db/database.py — 新增 price_ticks 表 DDL、insert/get_price_ticks/cleanup_old_ticks

## 阶段二：配置层

- [ ] 2.1 config/settings.py — 新增 price_tick_interval_seconds、price_tick_enabled

## 阶段三：采集层

- [ ] 3.1 collectors/price_ticker.py — 新建 PriceTicker：高频采集所有 token 实时价格（支持批量接口 + 单地址降级）

## 阶段四：信号层

- [ ] 4.1 signals/candle_analyzer.py — 新建 CandleAnalyzer：烛图模式检测 + 反转预警
  - [ ] 价格序列方向判定（含 flat 过滤）
  - [ ] 趋势/反转模式扫描
  - [ ] 趋势强度分级
  - [ ] 严重度计算（反转根数 × 趋势系数）
  - [ ] 冷却状态管理（per token per level）

## 阶段五：通知层

- [ ] 5.1 notifiers/feishu_notifier.py — 新增 reversal_bearish/bullish 卡片模板
  - [ ] CARD_HEADER_TEMPLATES 条目
  - [ ] 预警详情包含趋势段和反转段的价格变化 + 成交量

## 阶段六：调度集成

- [ ] 6.1 scheduler/scheduler.py — 集成 PriceTicker + CandleAnalyzer 到调度器
  - [ ] price_tick 定时任务
  - [ ] candle_analyzer 在 tick 后运行
  - [ ] 飞书推送
