---
id: gold-scheduled-report
name: 定时报告生成
events:
  - ScheduledTask
  - SessionStart
description: |
  在定时任务触发时自动生成并发送黄金跟踪报告。
  支持根据日期自动选择报告格式，并发送指定渠道。
---

# 定时报告生成 Hook

## 触发条件

当 WorkBuddy 定时任务触发时，自动执行黄金报告生成流程。

## 执行流程

```
定时触发
    ↓
检查今日是否为交易日（周一至周五）
    ↓
是 → 执行 /gold-fetch 采集数据
    ↓
执行 /gold-report 生成报告
    ↓
根据配置发送报告（控制台/文件/其他渠道）
    ↓
清理30天前历史报告
    ↓
完成
```

## 配置方式

在 WorkBuddy 中设置定时任务：

```
任务名称：黄金日度跟踪
执行频率：FREQ=DAILY;BYHOUR=15;BYMINUTE=30;BYDAY=MO,TU,WE,TH,FR
执行命令：/gold-report --output both
```

## 报告格式自动选择

Hook 会根据以下规则自动选择报告格式：

| 条件 | 选择格式 | 说明 |
|------|---------|------|
| 周一 | 格式C（周度深度） | 包含本周回顾和下周展望 |
| FOMC前后1天 | 格式B（事件快报） | 聚焦美联储决策 |
| 9月1日/11月1日 | 格式B（事件快报） | 季节性提醒 |
| 预警等级≥橙色 | 格式B（事件快报） | 风险提示 |
| 其他工作日 | 格式A（简报） | 3行核心信息 |

## 输出处理

### 控制台输出
- 在 WorkBuddy 聊天窗口显示报告
- 适合实时查看

### 文件输出
- 保存至 `memory/YYYY-MM-DD.md`
- 便于历史查询和归档

### 多渠道发送（扩展）

可通过配置集成其他发送渠道：
- 邮件
- 企业微信
- 钉钉
- 飞书

## 日志记录

每次执行记录以下信息：
- 执行时间
- 报告格式
- 预警等级
- 数据状态（正常/降级）
- 发送状态

## 故障处理

| 场景 | 处理方式 |
|------|---------|
| API采集失败 | 使用缓存数据，标记"(缓存)" |
| 报告生成失败 | 记录错误日志，下次执行时补发 |
| 发送失败 | 标记为待发送，下次重试 |

## 示例配置

### 基础配置（每日15:30）

```json
{
  "schedule": "FREQ=DAILY;BYHOUR=15;BYMINUTE=30;BYDAY=MO,TU,WE,TH,FR",
  "command": "/gold-report --output both",
  "enabled": true
}
```

### 高级配置（多时段）

```json
{
  "schedules": [
    {
      "name": "早盘简报",
      "schedule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=30;BYDAY=MO,TU,WE,TH,FR",
      "command": "/gold-report --format A"
    },
    {
      "name": "收盘报告",
      "schedule": "FREQ=DAILY;BYHOUR=15;BYMINUTE=30;BYDAY=MO,TU,WE,TH,FR",
      "command": "/gold-report --output both"
    }
  ]
}
```
