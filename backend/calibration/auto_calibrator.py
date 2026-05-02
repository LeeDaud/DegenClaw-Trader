"""全自动校准 — 回测 + 参数搜索 + 安全机制"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from db.database import Database
from db.models import utc_now_iso

logger = logging.getLogger(__name__)

# 参数搜索空间
SEARCH_SPACE: dict[str, list[float | int]] = {
    "rank_trend_min_magnitude": [2, 3, 4, 5, 6],
    "pnl_surge_min_24h": [12.0, 15.0, 18.0, 20.0, 25.0],
    "pnl_dump_max_24h": [-20.0, -15.0, -12.0, -10.0],
    "wr_surge_min": [5.0, 8.0, 10.0, 12.0],
    "wr_dump_max": [-12.0, -10.0, -8.0, -5.0],
    "combined_surge_score": [30, 35, 40, 45],
    "combined_dump_score": [30, 35, 40, 45],
    "confirmation_count": [2, 3, 4],
}

# 搜索阶段常量
_PHASE1_GROUPS: dict[str, list[str]] = {
    "rank": ["rank_trend_min_magnitude"],
    "pnl": ["pnl_surge_min_24h", "pnl_dump_max_24h"],
    "wr": ["wr_surge_min", "wr_dump_max"],
    "combined": ["combined_surge_score", "combined_dump_score"],
}

# 安全边界
_F1_DEGRADE_LIMIT = 0.95       # 新参数 F1 不能低于旧参数的 95%
_MAX_ALERTS_PER_HOUR = 8       # 校准后每小时最多 8 条 Alert
_MAX_CALIBRATION_HISTORY = 20  # 保留最多 20 条历史


class AutoCalibrator:
    """全自动校准器

    职责：
    1. 阶段式参数搜索（先逐类型优化，再联合精调）
    2. 回测验证
    3. 安全检查和持久化
    """

    def __init__(self, database: Database) -> None:
        self.db = database

    def full_calibrate(self) -> dict[str, Any]:
        """运行一次完整校准

        Returns:
            {"success": bool, "old_params": ..., "new_params": ...,
             "old_f1": float, "new_f1": float, "improvement_pct": float}
        """
        from calibration.backtest import BacktestEngine

        engine = BacktestEngine(self.db)

        # 获取当前生产参数
        current_params = self._load_current_params()

        # Phase 1：逐信号类型优化
        phase1_params = dict(current_params)
        for group_name, keys in _PHASE1_GROUPS.items():
            best = self._optimize_group(engine, phase1_params, group_name, keys)
            phase1_params.update(best)

        # Phase 2：联合精调（缩小范围）
        phase2_params = self._joint_refine(engine, phase1_params)

        # Phase 3：验证
        valid = self._validate(engine, current_params, phase2_params)
        if not valid:
            logger.warning("校准验证未通过，保留当前参数")
            return {
                "success": False,
                "reason": "validation_failed",
                "current_params": current_params,
            }

        # 持久化
        self._save_calibration(current_params, phase2_params, engine)

        logger.info("校准完成: F1 %.3f → %.3f (%.1f%%)",
                    self._compute_f1(engine, current_params),
                    self._compute_f1(engine, phase2_params),
                    self._improvement_pct(engine, current_params, phase2_params))

        return {
            "success": True,
            "old_params": current_params,
            "new_params": phase2_params,
            "old_f1": self._compute_f1(engine, current_params),
            "new_f1": self._compute_f1(engine, phase2_params),
        }

    def quick_calibrate(self) -> dict[str, Any]:
        """快速校准 — 只调 3 个最敏感参数

        Returns: 同 full_calibrate
        """
        from calibration.backtest import BacktestEngine

        engine = BacktestEngine(self.db)
        current_params = self._load_current_params()
        candidate = dict(current_params)

        sensitive_keys = ["rank_trend_min_magnitude", "pnl_surge_min_24h", "combined_surge_score"]
        for key in sensitive_keys:
            if key not in SEARCH_SPACE:
                continue
            values = [v for v in SEARCH_SPACE[key] if v != current_params.get(key)]
            if not values:
                continue
            best_val = values[0]
            best_f1 = -1.0
            for v in values:
                test_params = dict(candidate)
                test_params[key] = v
                result = engine.run(test_params)
                f1 = result.f1_score
                if f1 > best_f1:
                    best_f1 = f1
                    best_val = v
            candidate[key] = best_val

        valid = self._validate(engine, current_params, candidate)
        if not valid:
            return {"success": False, "reason": "validation_failed", "current_params": current_params}

        self._save_calibration(current_params, candidate, engine)
        return {
            "success": True,
            "old_params": current_params,
            "new_params": candidate,
            "old_f1": self._compute_f1(engine, current_params),
            "new_f1": self._compute_f1(engine, candidate),
        }

    # ── 内部方法 ────────────────────────────────────────────────────

    def _load_current_params(self) -> dict[str, Any]:
        """从 DB 加载当前信号参数"""
        raw = self.db.get_all_config()
        params: dict[str, Any] = {}
        key_map = {
            "rank_trend_min_magnitude": int,
            "rank_trend_consistency": float,
            "pnl_surge_min_24h": float,
            "pnl_dump_max_24h": float,
            "wr_surge_min": float,
            "wr_dump_max": float,
            "combined_surge_score": int,
            "combined_dump_score": int,
            "confirmation_count": int,
        }
        for k, converter in key_map.items():
            raw_val = raw.get(k)
            if raw_val is not None:
                try:
                    params[k] = converter(raw_val)
                except (ValueError, TypeError):
                    continue
        return params

    def _optimize_group(
        self,
        engine: Any,
        base_params: dict,
        group_name: str,
        keys: list[str],
    ) -> dict[str, Any]:
        """Phase 1：独立优化一组参数"""
        best_params = dict(base_params)
        best_f1 = -1.0

        # 对每个 key 独立搜索最优值
        for key in keys:
            if key not in SEARCH_SPACE:
                continue
            for val in SEARCH_SPACE[key]:
                test_params = dict(best_params)
                test_params[key] = val
                result = engine.run(test_params)
                if result.f1_score > best_f1:
                    best_f1 = result.f1_score
                    best_params[key] = val

        return {k: best_params.get(k, base_params.get(k)) for k in keys}

    def _joint_refine(self, engine: Any, phase1_params: dict) -> dict[str, Any]:
        """Phase 2：联合精调"""
        best_params = dict(phase1_params)
        best_f1 = self._compute_f1(engine, best_params)

        # 在 Phase 1 最优值周围微调（±1 步）
        keys = list(SEARCH_SPACE.keys())
        for key in keys:
            values = SEARCH_SPACE[key]
            current = best_params.get(key)
            if current is None:
                continue
            idx = values.index(current) if current in values else -1
            if idx < 0:
                continue
            neighbors = []
            if idx > 0:
                neighbors.append(values[idx - 1])
            if idx < len(values) - 1:
                neighbors.append(values[idx + 1])
            for nv in neighbors:
                test = dict(best_params)
                test[key] = nv
                f1 = self._compute_f1(engine, test)
                if f1 > best_f1:
                    best_f1 = f1
                    best_params[key] = nv

        return best_params

    def _compute_f1(self, engine: Any, params: dict) -> float:
        """计算给定参数的 F1 分数"""
        result = engine.run(params)
        return result.f1_score

    def _improvement_pct(self, engine: Any, old: dict, new: dict) -> float:
        old_f1 = self._compute_f1(engine, old)
        new_f1 = self._compute_f1(engine, new)
        if old_f1 <= 0:
            return 0.0
        return (new_f1 - old_f1) / old_f1 * 100

    def _validate(self, engine: Any, current_params: dict, candidate_params: dict) -> bool:
        """安全验证

        检查项：
        1. 新参数 F1 >= 旧参数 F1 × _F1_DEGRADE_LIMIT
        2. 新参数生成的总信号数不能超过安全上限
        """
        current_result = engine.run(current_params)
        candidate_result = engine.run(candidate_params)

        current_f1 = current_result.f1_score
        candidate_f1 = candidate_result.f1_score

        # 检查 1：F1 不退化超过 5%
        if current_f1 > 0 and candidate_f1 < current_f1 * _F1_DEGRADE_LIMIT:
            logger.warning("安全检查失败: F1 %.3f → %.3f (退化 > 5%%)",
                           current_f1, candidate_f1)
            return False

        # 检查 2：信号数不暴增
        max_signals = current_result.total_signals * 1.5 + 5
        if candidate_result.total_signals > max_signals:
            logger.warning("安全检查失败: 信号数 %d → %d (超出 %.0f)",
                           current_result.total_signals, candidate_result.total_signals, max_signals)
            return False

        return True

    def _save_calibration(
        self,
        old_params: dict,
        new_params: dict,
        engine: Any,
    ) -> None:
        """持久化校准结果"""
        now = utc_now_iso()
        old_f1 = self._compute_f1(engine, old_params)
        new_f1 = self._compute_f1(engine, new_params)
        baseline_result = engine.run(old_params)
        new_result = engine.run(new_params)

        # 写入 calibration 记录
        record = {
            "calibrated_at": now,
            "params": json.dumps(new_params, ensure_ascii=False),
            "f1_score": new_f1,
            "precision": new_result.precision,
            "recall": new_result.recall,
            "total_signals": new_result.total_signals,
            "baseline_f1": old_f1,
            "baseline_precision": baseline_result.precision,
            "baseline_recall": baseline_result.recall,
            "baseline_signals": baseline_result.total_signals,
            "active": 1,
        }
        self.db.insert_calibration_record(record)

        # 去激活旧记录
        self.db.deactivate_old_calibrations(keep_latest=_MAX_CALIBRATION_HISTORY)

        # 更新生产配置
        for key, val in new_params.items():
            str_val = f"{val:.1f}" if isinstance(val, float) else str(val)
            self.db.set_config(key, str_val)

        logger.info("校准参数已持久化: %s", new_params)
