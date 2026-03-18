"""
黄金市场数据采集脚本 v4.1 (WorkBuddy Plugin版)
方案四核心：稳健API调用，失败时静默降级到缓存，不触发补救搜索

功能特性：
  1. 多合约自动尝试（期货合约名称每季度变化，自动发现当季合约）
  2. 接口失败静默降级，标注 (缓存) 后继续，不抛异常
  3. SGE 品种名称两种写法都尝试（Au9999 / AU9999）
  4. 输出结构化 today_data.json，包含数据来源标记
  5. 差量计算逻辑完整覆盖所有关键指标
  6. 季节性周期检测（小桥流水人家方法论）
  7. 自动清理30天前历史报告
"""

import urllib.request
import json
import os
from datetime import datetime, date, timedelta

BASE_URL = "https://www.codebuddy.cn/v2/tool/financedata"
DATA_DIR  = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(DATA_DIR, "../data/gold_tracker_cache.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "../data/today_data.json")
MEMORY_DIR = os.path.join(DATA_DIR, "../memory")

# ── 工具函数 ────────────────────────────────────────────────

def call_api(api_name, params, fields="", timeout=15):
    """调用金融数据接口，任何异常返回 {"error": reason}，不抛出"""
    payload = {"api_name": api_name, "params": params}
    if fields:
        payload["fields"] = fields
    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            BASE_URL, data=data,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            # 统一检查接口级错误码
            if isinstance(result, dict) and result.get("code") not in (None, 0, 200, "0", "200"):
                return {"error": f"api_error code={result.get('code')} msg={result.get('msg','')}"}
            return result
    except Exception as e:
        return {"error": str(e)}

def parse_items(resp):
    """从接口响应中提取 list[dict]，失败返回空列表"""
    try:
        items  = resp["data"]["items"]
        fields = resp["data"]["fields"]
        return [dict(zip(fields, row)) for row in items]
    except Exception:
        return []

def load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def today_str():
    return date.today().strftime("%Y%m%d")

def recent_trading_dates(n=5):
    """返回最近 n 个自然日的日期字符串列表（含今天），用于补查"""
    result = []
    d = date.today()
    while len(result) < n:
        result.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return result

def pct_change(new, old):
    if new is None or old is None or old == 0:
        return None
    return round((new - old) / abs(old) * 100, 3)

def exceeds_threshold(new, old, pct_thr=None, abs_thr=None):
    if new is None or old is None:
        return False
    if pct_thr is not None:
        p = abs(pct_change(new, old) or 0)
        if p >= pct_thr:
            return True
    if abs_thr is not None:
        if abs(new - old) >= abs_thr:
            return True
    return False

def cleanup_old_reports(days_to_keep=30):
    """
    清理30天前的历史报告文件（memory/YYYY-MM-DD.md）
    仅在报告生成成功后调用
    """
    if not os.path.exists(MEMORY_DIR):
        print(f"  清理：memory 目录不存在，跳过")
        return

    cutoff_date = date.today() - timedelta(days=days_to_keep)
    deleted_count = 0

    for filename in os.listdir(MEMORY_DIR):
        # 匹配 YYYY-MM-DD.md 格式的报告文件
        if filename.endswith(".md") and filename.count("-") == 2:
            try:
                # 提取日期部分
                date_str = filename.replace(".md", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if file_date < cutoff_date:
                    file_path = os.path.join(MEMORY_DIR, filename)
                    os.remove(file_path)
                    print(f"  清理：删除 {filename}（{file_date}）")
                    deleted_count += 1
            except (ValueError, OSError) as e:
                # 文件名格式不正确或删除失败，跳过
                pass

    if deleted_count == 0:
        print(f"  清理：无30天前报告需要删除")
    else:
        print(f"  清理：共删除 {deleted_count} 份30天前的历史报告")

def get_seasonal_period(current_date=None):
    """
    根据当前日期判断所处的季节性周期（小桥流水人家方法论）
    返回：period_info 或 None
    """
    if current_date is None:
        current_date = date.today()
    
    month = current_date.month
    
    # 季节性周期定义
    periods = {
        (9, 10): {
            "name": "9-10月回调窗口",
            "signal": "警惕回调",
            "action": "可减仓或观望",
            "expected_move": "5-10%回调",
            "reason": "季节性消费需求变化、宏观数据发布周期",
            "priority": "high"
        },
        (11, 12): {
            "name": "11-12月布局窗口",
            "signal": "逢低布局",
            "action": "持有待涨",
            "expected_move": "解套机会，误差1-2个月",
            "reason": "年底上涨规律，康波萧条期避险需求",
            "priority": "high"
        },
        (1, 2): {
            "name": "年初上涨期",
            "signal": "延续涨势",
            "action": "维持仓位",
            "expected_move": "继续上涨",
            "reason": "春节需求、年初资金配置",
            "priority": "medium"
        },
    }
    
    # 检查是否在关键月份
    for months, info in periods.items():
        if month in months:
            return info
    
    # 3-8月为震荡期
    return {
        "name": "3-8月震荡期",
        "signal": "震荡整理",
        "action": "定投或观望",
        "expected_move": "区间震荡",
        "reason": "缺乏明确季节性驱动",
        "priority": "low"
    }

def check_seasonal_reminder(cache):
    """
    检查是否需要显示季节性提醒
    在关键月份转换时触发提醒
    """
    today = date.today()
    month = today.month
    
    # 从缓存中获取上次提醒的月份
    last_reminder_month = cache.get("seasonal_last_reminder_month", 0)
    
    # 关键月份：9月（回调预警）、11月（布局机会）
    key_months = [9, 11]
    
    if month in key_months and month != last_reminder_month:
        return True, get_seasonal_period(today)
    
    return False, None

# ── 数据采集函数 ─────────────────────────────────────────────

def fetch_etf_518880(today, last_val):
    """采集 518880 ETF 当日行情；今日无数据时向前最多查5天"""
    fields = "trade_date,close,pct_chg,vol,amount"
    dates_to_try = recent_trading_dates(5)
    for dt in dates_to_try:
        r = call_api("fund_daily",
                     {"ts_code": "518880.SH", "start_date": dt, "end_date": today},
                     fields)
        rows = parse_items(r)
        if rows:
            # 取最新一条
            row = sorted(rows, key=lambda x: x.get("trade_date",""), reverse=True)[0]
            is_today = row.get("trade_date","").replace("-","") == today
            label = "" if is_today else f" (数据日期 {row['trade_date']})"
            val = float(row.get("close") or 0)
            pct = float(row.get("pct_chg") or 0)
            print(f"  518880: {val} 元  ({pct:+.2f}%){label}")
            return {
                "value": val, "pct_chg": pct,
                "vol": row.get("vol"), "amount": row.get("amount"),
                "trade_date": row.get("trade_date"),
                "source": "api" if is_today else "api_prev"
            }
        if not r.get("error"):
            break  # 接口通但无数据，不再重试
    print(f"  518880: 接口无数据，使用缓存 {last_val}")
    return {"value": last_val, "source": "cache"}

def fetch_au9999(today, last_val):
    """采集 SGE AU9999 定盘价；品种名称两种写法都尝试"""
    # SGE 接口建议用范围查
    start = (date.today() - timedelta(days=5)).strftime("%Y%m%d")
    r = call_api("sge_daily",
                 {"start_date": start, "end_date": today},
                 "trade_date,product,open,high,low,close,vol,amount")
    rows = parse_items(r)
    # 匹配品种（两种写法）
    for product_name in ("Au9999", "AU9999", "au9999"):
        matched = [row for row in rows if row.get("product","").upper() == "AU9999"]
        if matched:
            row = sorted(matched, key=lambda x: x.get("trade_date",""), reverse=True)[0]
            val = float(row.get("close") or 0)
            is_today = row.get("trade_date","").replace("-","") == today
            label = "" if is_today else f" (数据日期 {row['trade_date']})"
            print(f"  AU9999: {val} 元/克{label}")
            return {
                "value": val,
                "trade_date": row.get("trade_date"),
                "source": "api" if is_today else "api_prev"
            }
        break  # 只需尝试一次过滤
    print(f"  AU9999: 接口无数据，使用缓存 {last_val}")
    return {"value": last_val, "source": "cache"}

def fetch_shfe_gold(today, last_val):
    """
    采集 SHFE 黄金主力期货；合约代码每季度变化，自动按季度尝试。
    当季合约格式：AU2506.SHFE（年份后两位 + 月份两位）
    """
    # 生成候选合约列表（当季 + 前后两季）
    d = date.today()
    candidates = []
    for delta_months in (0, 2, -2, 4, -4):
        m = d.month + delta_months
        y = d.year
        while m > 12: m -= 12; y += 1
        while m < 1:  m += 12; y -= 1
        # SHFE黄金合约月份：2/4/6/8/10/12（偶数月）
        target_month = m if m % 2 == 0 else m + 1
        if target_month > 12: target_month = 2; y += 1
        code = f"AU{str(y)[-2:]}{target_month:02d}.SHFE"
        if code not in candidates:
            candidates.append(code)

    start = (date.today() - timedelta(days=5)).strftime("%Y%m%d")
    for code in candidates:
        r = call_api("fut_daily",
                     {"ts_code": code, "start_date": start, "end_date": today},
                     "trade_date,ts_code,close,pct_chg,vol,oi")
        rows = parse_items(r)
        if rows:
            row = sorted(rows, key=lambda x: x.get("trade_date",""), reverse=True)[0]
            val = float(row.get("close") or 0)
            print(f"  SHFE黄金 {code}: {val} 元/克")
            return {
                "value": val, "contract": code,
                "trade_date": row.get("trade_date"),
                "source": "api"
            }

    print(f"  SHFE黄金: 所有候选合约无数据，使用缓存 {last_val}")
    return {"value": last_val, "source": "cache"}

# ── 差量分析 ─────────────────────────────────────────────────

def compute_delta(fetched, last, thresholds):
    """
    比较今日值与上次值，返回：
      changed_fields: 超阈值的字段列表（含说明）
      all_same:       True 表示全部在阈值内
    """
    checks = [
        ("etf_518880",   fetched.get("etf_518880"),   last.get("etf_518880"),
         thresholds.get("etf_price_pct", 0.5), None, "元"),
        ("au9999_cny",   fetched.get("au9999_cny"),   last.get("au9999_cny"),
         0.5, None, "元/克"),
        ("gold_usd",     fetched.get("gold_usd"),     last.get("gold_usd"),
         0.5, None, "$/盎司"),
        ("wti_usd",      fetched.get("wti_usd"),      last.get("wti_usd"),
         thresholds.get("oil_price_pct", 1.0), None, "$/桶"),
        ("dxy",          fetched.get("dxy"),           last.get("dxy"),
         None, thresholds.get("dxy", 0.3), ""),
        ("tips_10y_pct", fetched.get("tips_10y_pct"), last.get("tips_10y_pct"),
         None, thresholds.get("tips_bp", 5) / 100, "%"),
        ("rsi_14",       fetched.get("rsi_14"),        last.get("rsi_14"),
         None, thresholds.get("rsi_pts", 5), ""),
        ("gold_oil_ratio", fetched.get("gold_oil_ratio"), last.get("gold_oil_ratio"),
         None, thresholds.get("gold_oil_ratio", 2.0), ""),
    ]

    changed = []
    for name, new, old, pct_thr, abs_thr, unit in checks:
        if new is None or old is None:
            continue
        if exceeds_threshold(new, old, pct_thr, abs_thr):
            pct = pct_change(new, old)
            sign = "+" if new >= old else ""
            pct_str = f" ({sign}{pct}%)" if pct is not None else ""
            changed.append({
                "field": name,
                "old": old, "new": new, "unit": unit,
                "summary": f"{name}: {old}{unit} → {new}{unit}{pct_str}"
            })

    # 叙事切换
    old_narr = last.get("narrative","")
    new_narr = fetched.get("narrative", old_narr)
    if new_narr and new_narr != old_narr:
        changed.append({
            "field": "narrative",
            "old": old_narr, "new": new_narr, "unit": "",
            "summary": f"⚡ 叙事切换: [{old_narr}] → [{new_narr}]"
        })

    return changed, len(changed) == 0

# ── 主流程 ───────────────────────────────────────────────────

def main():
    today    = today_str()
    cache    = load_cache()
    last     = cache.get("last_values", {})
    thresholds = cache.get("thresholds", {})

    print(f"\n{'='*52}")
    print(f"  🥇 黄金市场数据采集 v4.1  —  {today}")
    print(f"{'='*52}")

    # ── 采集各接口 ──
    etf_result   = fetch_etf_518880(today, last.get("etf_518880"))
    au_result    = fetch_au9999(today, last.get("au9999_cny"))
    shfe_result  = fetch_shfe_gold(today, last.get("shfe_cny"))

    # ── 组装今日数据（国际价格由AI搜索补充，此处用缓存占位）──
    fetched = {
        "date":           today,
        "etf_518880":     etf_result["value"],
        "etf_pct_chg":    etf_result.get("pct_chg"),
        "etf_trade_date": etf_result.get("trade_date"),
        "au9999_cny":     au_result["value"],
        "au9999_trade_date": au_result.get("trade_date"),
        "shfe_cny":       shfe_result["value"],
        "shfe_contract":  shfe_result.get("contract"),
        # 以下由AI搜索后填充，此处保留上次值
        "gold_usd":       last.get("gold_usd"),
        "wti_usd":        last.get("wti_usd"),
        "brent_usd":      last.get("brent_usd"),
        "dxy":            last.get("dxy"),
        "tips_10y_pct":   last.get("tips_10y_pct"),
        "us10y_pct":      last.get("us10y_pct"),
        "rsi_14":         last.get("rsi_14"),
        "vix":            last.get("vix"),
        "narrative":      last.get("narrative"),
        "scenario":       last.get("scenario"),
        "alert_level":    last.get("alert_level"),
        "gold_oil_ratio": (
            round(last["gold_usd"] / last["wti_usd"], 2)
            if last.get("gold_usd") and last.get("wti_usd")
            else last.get("gold_oil_ratio")
        ),
    }

    # ── 数据来源汇总 ──
    sources = {
        "etf_518880": etf_result["source"],
        "au9999_cny": au_result["source"],
        "shfe_cny":   shfe_result["source"],
        "gold_usd":   "needs_search",
        "wti_usd":    "needs_search",
        "dxy":        "needs_search",
        "tips_10y_pct": "needs_search",
    }

    # ── 差量计算 ──
    changed_fields, all_same = compute_delta(fetched, last, thresholds)

    print(f"\n{'─'*52}")
    print("差量比对：")
    if all_same:
        print("  今日所有可用指标变化均在阈值内 (缓存数据)")
    else:
        for cf in changed_fields:
            print(f"  ⚡ {cf['summary']}")

    # ── 确定报告类型 ──
    narrative_changed = any(cf["field"] == "narrative" for cf in changed_fields)
    is_monday = date.today().weekday() == 0   # 周一
    # FOMC日由缓存中的特殊标记决定，此处用占位
    is_fomc_day = cache.get("is_fomc_day", False)

    report_type = "A"  # 普通格式
    if narrative_changed or is_fomc_day:
        report_type = "B"  # 完整格式

    # ── 写出结构化输出 ──
    output = {
        "report_type":     report_type,
        "date":            today,
        "is_monday":       is_monday,
        "is_fomc_day":     is_fomc_day,
        "all_same":        all_same,
        "fetched":         fetched,
        "last":            {k: last.get(k) for k in fetched.keys()},
        "sources":         sources,
        "changed_fields":  changed_fields,
        "needs_search":    [k for k, v in sources.items() if v == "needs_search"],
        "narrative_changed": narrative_changed,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n报告类型: 格式{'A（普通日简报）' if report_type=='A' else 'B（重要日完整版）'}")
    print(f"需要AI补充搜索的字段: {output['needs_search']}")
    print(f"输出已写入 today_data.json")

    # ── 季节性周期检测（小桥流水人家方法论） ──
    print(f"\n{'─'*52}")
    seasonal_info = get_seasonal_period()
    print(f"季节性周期：{seasonal_info['name']}")
    print(f"  信号：{seasonal_info['signal']} | 建议：{seasonal_info['action']}")
    
    # 检查是否需要触发季节性提醒
    need_reminder, reminder_info = check_seasonal_reminder(cache)
    if need_reminder:
        print(f"  ⚡ 季节性提醒：进入{reminder_info['name']}，建议{reminder_info['action']}")
    
    # ── 清理30天前历史报告 ──
    print(f"\n{'─'*52}")
    cleanup_old_reports(days_to_keep=30)
    print()

    # 更新输出，加入季节性信息
    output["seasonal_info"] = seasonal_info
    output["seasonal_reminder"] = need_reminder
    
    # 更新缓存中的季节性提醒状态
    if need_reminder:
        cache["seasonal_last_reminder_month"] = date.today().month
        save_cache(cache)

    return output

if __name__ == "__main__":
    main()
