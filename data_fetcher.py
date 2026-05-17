# ============================================
# A股数据获取脚本
# 使用 AKShare 获取股票数据，输出JSON供网站使用
# 用法: python data_fetcher.py [--config config.yaml] [--output data/]
# ============================================

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import akshare as ak
    import yaml
    import pandas as pd
except ImportError:
    print("正在安装依赖...")
    os.system("pip install akshare pyyaml pandas -q")
    import akshare as ak
    import yaml
    import pandas as pd


def load_config(config_path):
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def fetch_stock_info(code, market):
    """获取单只股票的基本信息"""
    try:
        # 获取实时行情
        if market == 'SH':
            symbol = f"sh{code}"
        else:
            symbol = f"sz{code}"

        df = ak.stock_zh_a_spot_em()
        stock_row = df[df['代码'] == code]

        if stock_row.empty:
            return None

        row = stock_row.iloc[0]
        info = {
            'code': str(code),
            'name': row.get('名称', ''),
            'price': float(row.get('最新价', 0) or 0),
            'change_pct': float(row.get('涨跌幅', 0) or 0),
            'volume': float(row.get('成交量', 0) or 0),
            'amount': float(row.get('成交额', 0) or 0),
            'high': float(row.get('最高', 0) or 0),
            'low': float(row.get('最低', 0) or 0),
            'open': float(row.get('今开', 0) or 0),
            'prev_close': float(row.get('昨收', 0) or 0),
            'market_cap': float(row.get('总市值', 0) or 0),
        }

        # 获取PE/PB等财务指标（从实时行情补充）
        try:
            # 尝试从东方财富获取估值指标
            df_val = ak.stock_zh_valuation_baidu(symbol=code)
            if not df_val.empty:
                latest = df_val.iloc[0]
                info['pe_ttm'] = float(latest.get('pe_ttm', 0) or 0)
                info['pe_static'] = float(latest.get('pe', 0) or 0)
                info['pb'] = float(latest.get('pb', 0) or 0)
        except Exception:
            try:
                # 备选方案：用个股信息接口
                info_df = ak.stock_individual_info_em(symbol=code)
                if not info_df.empty:
                    for _, row in info_df.iterrows():
                        item = str(row.get('item', ''))
                        val = row.get('value', '0')
                        if '市盈率' in item:
                            try: info['pe_ttm'] = float(str(val).replace('--','0'))
                            except: pass
                        elif '市净率' in item:
                            try: info['pb'] = float(str(val).replace('--','0'))
                            except: pass
            except Exception:
                pass
        if not info.get('pe_ttm'):
            info['pe_ttm'] = None
        if not info.get('pb'):
            info['pb'] = None

        # 获取历史价格（用于图表）
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d')
            df_hist = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date,
                adjust="qfq"
            )
            if not df_hist.empty:
                hist_data = []
                for _, r in df_hist.tail(120).iterrows():
                    hist_data.append({
                        'date': str(r.get('日期', '')),
                        'close': float(r.get('收盘', 0) or 0),
                        'volume': int(r.get('成交量', 0) or 0),
                        'change_pct': float(r.get('涨跌幅', 0) or 0)
                    })
                info['history'] = hist_data

                # 计算MA20
                closes = [h['close'] for h in hist_data if h['close'] > 0]
                if len(closes) >= 20:
                    ma20 = sum(closes[-20:]) / 20
                    info['ma20'] = round(ma20, 2)
                    info['price_vs_ma20'] = round((info['price'] - ma20) / ma20 * 100, 2)

        except Exception as e:
            print(f"  [警告] 获取{code}历史数据失败: {e}")

        # 获取财务数据（利润增速、ROE等）
        try:
            df_fin = ak.stock_financial_abstract_ths(symbol=code)
            if not df_fin.empty:
                latest_fin = df_fin.iloc[0]
                info['profit_growth'] = None
                info['roe'] = None
                for col in df_fin.columns:
                    col_str = str(col)
                    if ('净利润' in col_str and '增长' in col_str) and info['profit_growth'] is None:
                        val = latest_fin.get(col)
                        if val is not None:
                            try: info['profit_growth'] = round(float(val), 2)
                            except (ValueError, TypeError): pass
                    if ('ROE' in col_str or '净资产收益率' in col_str) and info['roe'] is None:
                        val = latest_fin.get(col)
                        if val is not None:
                            try: info['roe'] = round(float(val), 2)
                            except (ValueError, TypeError): pass
        except Exception as e:
            print(f"  [警告] 获取{code}财务数据失败: {e}")
            info['profit_growth'] = None
            info['roe'] = None

        return info

    except Exception as e:
        print(f"  [错误] 获取{code}({market})数据失败: {e}")
        return None


def fetch_sector_data(sector_config, output_dir):
    """获取单个板块的所有股票数据"""
    sector_id = sector_config['id']
    stocks = sector_config.get('stocks', [])
    indicators_cfg = sector_config.get('indicators', [])

    result = {
        'sector_id': sector_id,
        'name': sector_config['name'],
        'tag': sector_config.get('tag', ''),
        'description': sector_config.get('description', ''),
        'fetched_at': datetime.now().isoformat(),
        'stocks': [],
        'indicators': [],
    }

    all_stock_data = []

    for stock in stocks:
        print(f"  正在获取: {stock['name']} ({stock['code']})")
        stock_data = fetch_stock_info(stock['code'], stock.get('market', 'SH'))
        if stock_data:
            all_stock_data.append(stock_data)

    result['stocks'] = all_stock_data

    # 计算板块级别的指标值
    for ind_cfg in indicators_cfg:
        ind_key = ind_cfg['key']
        values = []
        for sd in all_stock_data:
            v = sd.get(ind_key)
            if v is not None and not (isinstance(v, float) and (v != v)):  # 排除NaN
                values.append(v)

        if values:
            avg_value = sum(values) / len(values)
        else:
            avg_value = None

        # 判断信号状态
        threshold_low = ind_cfg.get('threshold_low')
        threshold_high = ind_cfg.get('threshold_high')

        signal = 'neutral'
        if avg_value is not None:
            direction = ind_cfg.get('direction', '')
            if direction == 'low_is_better':
                if threshold_low and avg_value < threshold_low:
                    signal = 'good'
                elif threshold_high and avg_value > threshold_high:
                    signal = 'bad'
            elif direction == 'high_is_better':
                if threshold_high and avg_value > threshold_high:
                    signal = 'good'
                elif threshold_low and avg_value < threshold_low:
                    signal = 'bad'
            elif direction == 'range':
                if threshold_low and threshold_high:
                    if threshold_low <= avg_value <= threshold_high:
                        signal = 'good'
                    else:
                        signal = 'bad'

        result['indicators'].append({
            **ind_cfg,
            'current_value': avg_value,
            'signal': signal,
            'values_from_stocks': values,
        })

    # 计算整体信号状态
    good_count = sum(1 for i in result['indicators'] if i.get('signal') == 'good')
    bad_count = sum(1 for i in result['indicators'] if i.get('signal') == 'bad')
    total = len(result['indicators'])

    if total > 0:
        ratio = good_count / total
        if bad_count >= total * 0.6:
            result['overall_signal'] = 'danger'
            result['signal_message'] = '⚠️ 多数指标偏离理想区间，需警惕'
        elif ratio >= 0.6:
            result['overall_signal'] = 'safe'
            result['signal_message'] = '✅ 指标处于合理区间，继续观察'
        else:
            result['overall_signal'] = 'warning'
            result['signal_message'] = '🟡 部分指标接近临界点'
    else:
        result['overall_signal'] = 'warning'
        result['signal_message'] = '数据不足，等待更新'

    # 保存为JSON
    output_file = Path(output_dir) / f"{sector_id}.json"
    Path(output_file).mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(f"  ✅ 已保存: {output_file.name}")
    return result


def main():
    parser = argparse.ArgumentParser(description='A股投资监控数据获取')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('--output', default='data/', help='数据输出目录')
    parser.add_argument('--sectors', default=None, help='只获取指定板块ID，逗号分隔')
    args = parser.parse_args()

    config_path = args.config
    output_dir = args.output

    if not Path(config_path).exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)

    config = load_config(config_path)
    sectors = config.get('sectors', [])

    if args.sectors:
        filter_ids = [s.strip() for s in args.sectors.split(',')]
        sectors = [s for s in sectors if s['id'] in filter_ids]

    print(f"\n{'='*50}")
    print(f"📊 A股数据获取 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    all_results = []
    for sector in sectors:
        print(f"📌 板块: {sector['name']} ({sector['id']})")
        result = fetch_sector_data(sector, output_dir)
        all_results.append(result)
        print()

    # 保存汇总索引
    index_data = {
        'updated_at': datetime.now().isoformat(),
        'sectors': [
            {
                'id': r['sector_id'],
                'name': r['name'],
                'tag': r.get('tag'),
                'overall_signal': r.get('overall_signal'),
                'signal_message': r.get('signal_message'),
                'stock_count': len(r.get('stocks', [])),
                'fetched_at': r.get('fetched_at'),
            }
            for r in all_results
        ]
    }

    index_file = Path(output_dir) / 'index.json'
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"{'='*50}")
    print(f"✅ 完成! 共处理 {len(all_results)} 个板块")
    print(f"📁 数据目录: {Path(output_dir).resolve()}")
    print(f"{'='*50}\n")

    return all_results


if __name__ == '__main__':
    main()
