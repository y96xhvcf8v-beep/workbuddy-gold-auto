---
id: gold-setup
name: 初始化配置
shortcut: /gold-setup
description: |
  初始化黄金跟踪系统的配置文件和数据目录。
  首次使用或重置配置时执行。
arguments:
  - name: reset
    type: boolean
    description: 是否重置所有配置（谨慎使用）
    required: false
    default: false
---

# 初始化配置

初始化黄金跟踪系统的配置文件和数据目录。

## 执行内容

1. **创建目录结构**
   ```
   data/          # 数据文件目录
   memory/        # 历史报告目录
   scripts/       # 辅助脚本目录
   ```

2. **生成默认配置**
   - `data/gold_tracker_cache.json` - 缓存配置
   - 包含：阈值设置、季节性规则、预警参数

3. **检查依赖环境**
   - Python >= 3.8
   - 必要的Python包（urllib, json等内置包）

4. **初始化历史数据**
   - 创建空的今日数据文件模板
   - 设置初始缓存值

## 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--reset` | boolean | false | 重置所有配置（会清空历史数据） |

## 使用示例

```bash
# 首次初始化
/gold-setup

# 重置所有配置（谨慎！）
/gold-setup --reset
```

## 配置文件说明

### gold_tracker_cache.json

```json
{
  "last_sent_date": "",
  "last_values": {
    "gold_usd": null,
    "etf_518880": null,
    "wti_usd": null,
    "dxy": null,
    "tips_10y_pct": null,
    "rsi_14": null
  },
  "alert_level": "normal",
  "scenario": "FOMC观望期",
  "seasonal_rules": {
    "enabled": true,
    "source": "小桥流水人家",
    "current_period": null
  },
  "thresholds": {
    "gold_price_change": 0.5,
    "etf_price_change": 0.5,
    "oil_price_change": 1.0,
    "dxy_change": 0.3
  }
}
```

## 初始化后检查清单

- [ ] 目录结构已创建
- [ ] 配置文件已生成
- [ ] Python环境检查通过
- [ ] 首次数据采集测试成功

## 下一步

初始化完成后，执行：
```bash
/gold-fetch    # 测试数据采集
/gold-report   # 测试报告生成
```
