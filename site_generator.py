# ============================================
# 网站生成脚本 [已弃用]
# 当前网站架构为手动维护的 index.html + JS动态加载数据，
# 此脚本为 v1 版本遗留代码，仅保留作为参考。
# 如需生成板块详情页可复用 generate_detail_page() 函数。
# 用法: python site_generator.py [--config config.yaml] [--data data/] [--output output/]
# ============================================

import argparse
import base64
import json
import os
import re
from pathlib import Path
from datetime import datetime
from html import escape as html_escape

try:
    import yaml
except ImportError:
    os.system("pip install pyyaml -q")
    import yaml


# =====================================================
# HTML 模板片段
# =====================================================

HTML_HEADER = '''<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}{suffix}</title>
<link rel="stylesheet" href="{css_path}">
<meta name="description" content="{description}">
</head>
<body>
'''

NAVBAR = '''
<nav class="navbar">
  <div class="nav-inner">
    <a href="{home_url}" class="nav-brand">
      <span>月泽小猫猫的逻辑库</span>
    </a>
    <div class="nav-right">
      <div class="search-wrapper">
        <span class="search-icon">🔍</span>
        <input type="text" class="search-input" placeholder="搜索板块、股票..." />
      </div>
      <button class="theme-toggle" title="切换主题">🌙</button>
    </div>
  </div>
</nav>
'''

FOOTER = '''
<footer class="footer">
  <p>{footer_text}</p>
  <p style="margin-top:6px">数据来源：AKShare / 东方财富 | 仅供参考，不构成投资建议</p>
</footer>

<script src="{js_path}"></script>
</body>
</html>
'''

SIGNAL_ICONS = {
    'safe': '✅',
    'warning': '⚠️',
    'danger': '🔴',
}


# =====================================================
# 工具函数
# =====================================================

def read_file(path):
    p = Path(path)
    if p.exists():
        return p.read_text(encoding='utf-8')
    return ''


def md_to_html(md_text):
    """简易 Markdown 转 HTML"""
    if not md_text:
        return '<p style="color:var(--text-muted)">暂无详细逻辑说明...</p>'

    lines = md_text.split('\n')
    html_lines = []
    in_table = False
    in_list = False
    list_type = None

    for line in lines:
        stripped = line.strip()

        # 空行
        if not stripped:
            if in_table:
                html_lines.append('</table>')
                in_table = False
            if in_list:
                if list_type == 'ul':
                    html_lines.append('</ul>')
                else:
                    html_lines.append('</ol>')
                in_list = False
            continue

        # 标题
        if stripped.startswith('## '):
            html_lines.append(f'<h2>{stripped[3:]}</h2>')
        elif stripped.startswith('### '):
            html_lines.append(f'<h3>{stripped[4:]}</h3>')
        elif stripped.startswith('# '):
            html_lines.append(f'<h1>{stripped[2:]}</h1>')

        # 表格
        elif '|' in stripped and not in_table:
            html_lines.append('<table><thead>')
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            html_lines.append('<tr>' + ''.join(f'<th>{html_escape(c)}</th>' for c in cells) + '</tr>')
            html_lines.append('</thead><tbody>')
            in_table = True
        elif '|' in stripped and in_table:
            if re.match(r'^[\|\s\-:]+$', stripped):  # 分隔行
                continue
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            html_lines.append('<tr>' + ''.join(f'<td>{html_escape(c)}</td>' for c in cells) + '</tr>')

        # 无序列表
        elif stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list or list_type != 'ul':
                if in_list:
                    html_lines.append('</ol>' if list_type == 'ol' else '</ul>')
                html_lines.append('<ul>')
                in_list = True
                list_type = 'ul'
            html_lines.append(f'<li>{stripped[2:]}</li>')

        # 数字列表
        elif re.match(r'^\d+\.\s', stripped):
            if not in_list or list_type != 'ol':
                if in_list:
                    html_lines.append('</ul>' if list_type == 'ul' else '</ol>')
                html_lines.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = re.sub(r'^\d+\.\s', '', stripped)
            html_lines.append(f'<li>{content}</li>')

        # 斜体/强调
        elif stripped.startswith('*') and stripped.endswith('*'):
            html_lines.append(f'<em>{stripped[1:-1]}</em>')

        # 普通段落
        else:
            if in_table:
                html_lines.append('</table>')
                in_table = False
            if in_list:
                html_lines.append('</ul>' if list_type == 'ul' else '</ol>')
                in_list = False
            # 处理加粗
            processed = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
            html_lines.append(f'<p>{processed}</p>')

    if in_table:
        html_lines.append('</table>')
    if in_list:
        html_lines.append('</ul>' if list_type == 'ul' else '</ol>')

    return '\n'.join(html_lines)


def get_signal_class(signal):
    return {'safe': 'safe', 'warning': 'warning', 'danger': 'danger'}.get(signal, 'warning')


def format_value(val, unit='', decimals=2):
    if val is None:
        return '--'
    if isinstance(val, (int, float)):
        if abs(val) >= 100000000:
            return f'{val/100000000:.2f}亿{unit}'
        elif abs(val) >= 10000:
            return f'{val/10000:.2f}万{unit}'
        else:
            return f'{val:.{decimals}f}{unit}'
    return str(val)


def calc_bar_width(value, low, high, reverse=False):
    """计算进度条宽度和颜色"""
    if value is None or low is None or high is None:
        return 30, 'warn'

    range_v = high - low
    if range_v <= 0:
        return 50, 'warn'

    pct = max(0, min(100, ((value - low) / range_v) * 100))

    if reverse:
        if pct < 40:
            cls = 'good'
        elif pct > 70:
            cls = 'bad'
        else:
            cls = 'warn'
    else:
        if pct > 60:
            cls = 'good'
        elif pct < 30:
            cls = 'bad'
        else:
            cls = 'warn'

    return pct, cls


def generate_indicator_card(indicator, idx):
    """生成单个指标卡片的 HTML"""
    val = indicator.get('current_value')
    name = indicator['name']
    unit = indicator.get('unit', '')
    direction = indicator.get('direction', '')
    th_lo = indicator.get('threshold_low')
    th_hi = indicator.get('threshold_high')
    sig = indicator.get('signal', 'neutral')
    sig_cls = get_signal_class(sig)

    display_val = format_value(val, unit)

    # 确定数值颜色
    value_cls = ''
    if isinstance(val, (int, float)):
        if direction == 'low_is_better':
            if th_lo and val < th_lo: value_cls = 'up'
            elif th_hi and val > th_hi: value_cls = 'down'
        elif direction == 'high_is_better':
            if th_hi and val > th_hi: value_cls = 'up'
            elif th_lo and val < th_lo: value_cls = 'down'

    bar_w, bar_cls = calc_bar_width(val, th_lo, th_hi,
                                      reverse=(direction == 'low_is_better'))

    lo_str = format_value(th_lo, decimals=1) if th_lo else '--'
    hi_str = format_value(th_hi, decimals=1) if th_hi else '--'

    return f'''
      <div class="indicator-card">
        <div class="ind-name">{html_escape(name)}</div>
        <div class="ind-value {value_cls}">{display_val}</div>
        <div class="ind-bar"><div class="ind-bar-fill {bar_cls}" style="width:{bar_w}%"></div></div>
        <div class="ind-range"><span>低: {lo_str}</span><span>高: {hi_str}</span></div>
      </div>'''


def generate_chart_section(data_json, sector_name):
    """生成图表区域 HTML"""
    chart_data = {}
    has_history = False

    # 从股票历史数据中构建股价走势图
    for stock in data_json.get('stocks', []):
        history = stock.get('history', [])
        if history:
            has_history = True
            chart_data = {
                'type': 'line',
                'labels': [h['date'][5:].replace('-', '/') for h in history],
                'points': [{'date': h['date'], 'value': h['close']} for h in history],
                'title': f'{stock["name"]} 股价走势(120日)'
            }
            break  # 用第一只有数据的股票

    if not has_history:
        return ''

    return f'''
    <div class="chart-container" data-type="line" data-json='{json.dumps(chart_data, ensure_ascii=False)}'>
      <div class="section-label"><span class="icon">📈</span> 历史走势</div>
      <div class="chart-canvas-area"></div>
    </div>
'''


# =====================================================
# 页面生成函数
# =====================================================

def generate_homepage(config, index_data, css_rel, js_rel):
    """生成首页 HTML"""
    sectors = config.get('sectors', [])
    site_name = config.get('site', {}).get('name', '投资逻辑监控')
    subtitle = config.get('site', {}).get('subtitle', '')

    updated_at = index_data.get('updated_at', '')
    if updated_at:
        try:
            dt = datetime.fromisoformat(updated_at)
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            time_str = updated_at
    else:
        time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 构建数据映射
    sector_signals = {}
    for item in index_data.get('sectors', []):
        sector_signals[item['id']] = item

    # 板块卡片
    cards_html = ''
    for sector in sectors:
        sid = sector['id']
        sdata = sector_signals.get(sid, {})
        signal = sdata.get('overall_signal', 'watching')
        sig_msg = sdata.get('signal_message', sector.get('signal_message', '持续观察中'))
        sig_icon = SIGNAL_ICONS.get(signal, '🔵')
        sig_cls = get_signal_class(signal)

        # 取前3个迷你指标
        indicators = sector.get('indicators', [])
        mini_ind = ''
        for ind in indicators[:4]:
            # 尝试从实际数据取值
            actual_val = None
            data_file = Path(args.data) / f"{sid}.json"
            if data_file.exists():
                try:
                    djson = json.loads(data_file.read_text(encoding='utf-8'))
                    for di in djson.get('indicators', []):
                        if di.get('key') == ind['key']:
                            actual_val = di.get('current_value')
                            break
                except:
                    pass

            disp_val = format_value(actual_val, ind.get('unit', ''))
            mini_ind += f'''
              <div class="mini-indicator">
                <span class="label">{html_escape(ind['name'])}</span>
                <span class="value">{disp_val}</span>
              </div>'''

        # 关联的股票代码
        stocks_chips = ''
        for st in sector.get('stocks', [])[:3]:
            stocks_chips += f'<span class="stock-chip">{st["name"]}</span>'
        if len(sector.get('stocks', [])) > 3:
            stocks_chips += f'<span class="stock-chip">+{len(sector["stocks"])-3}</span>'

        # 构建完整可搜索文本（用于首页搜索）
        # 包含：板块名称、描述、标签、所有股票名+代码、指标名、逻辑文章关键词
        search_parts = [
            sector['name'],
            sector.get('description', ''),
            sector.get('tag', ''),
        ]
        # 股票名称和代码
        for st in sector.get('stocks', []):
            search_parts.append(st['name'])
            search_parts.append(st['code'])
        # 指标名称
        for ind in indicators:
            search_parts.append(ind.get('name', ''))
        # 逻辑文章（截取前500字符作为搜索索引）
        article_text = sector.get('logic_article', '') or ''
        # 去掉markdown符号，提取纯文本关键词
        article_clean = re.sub(r'[#*|>\-\[\]()]', ' ', article_text)
        article_clean = re.sub(r'\s+', ' ', article_clean).strip()
        search_parts.append(article_text[:500])
        full_search_text = ' '.join([p for p in search_parts if p])

        cards_html += f'''
    <div class="sector-card" data-tag="{html_escape(sector.get('tag',''))}" data-name="{html_escape(sector['name'])}" data-href="stocks/{sid}.html" data-search-text="{html_escape(full_search_text)}">
      <div class="card-header">
        <div class="card-title-row">
          <h3 class="card-title">{html_escape(sector['name'])}</h3>
          <span class="card-tag">{html_escape(sector.get('tag', ''))}</span>
        </div>
        <span class="signal-badge {sig_cls}">{sig_icon} {sig_msg}</span>
      </div>
      <div class="card-body">
        <p class="card-desc">{html_escape(sector.get('description', ''))}</p>
        <div class="card-indicators">{mini_ind}</div>
      </div>
      <div class="card-footer">
        <div class="stocks-list">{stocks_chips}</div>
        <a href="stocks/{sid}.html" class="view-link">查看详情</a>
      </div>
    </div>'''

    page = HTML_HEADER.format(
        title=f'{site_name}',
        suffix='',
        description=f'{site_name} - {subtitle}',
        css_path=css_rel,
    )
    page += NAVBAR.format(home_url='index.html')
    page += f'''
<main class="container">
  <div class="page-header">
    <h1>{site_name}</h1>
    <p class="subtitle">{subtitle}</p>
    <div class="last-update">
      <span class="dot"></span>
      最后更新：{time_str}
    </div>
  </div>

  <div class="sector-grid">
    {cards_html}
  </div>
</main>
'''
    page += FOOTER.format(
        footer_text=f'© {datetime.now().year} 月泽小猫猫的逻辑库 | 数据每日自动更新',
        js_path=js_rel,
    )

    return page


def generate_detail_page(config, sector_id, css_rel, js_rel):
    """生成板块详情页 HTML"""
    sector = None
    for s in config.get('sectors', []):
        if s['id'] == sector_id:
            sector = s
            break

    if not sector:
        return '<p>板块不存在</p>', 404

    # 读取该板块的数据
    data_file = Path(args.data) / f"{sector_id}.json"
    if data_file.exists():
        try:
            data_json = json.loads(data_file.read_text(encoding='utf-8'))
        except:
            data_json = {}
    else:
        data_json = {}

    site_name = config.get('site', {}).get('name', '投资逻辑监控')

    overall_sig = data_json.get('overall_signal', sector.get('signal_status', 'warning'))
    sig_msg = data_json.get('signal_message', sector.get('signal_message', '持续观察中'))
    sig_cls = get_signal_class(overall_sig)
    sig_icon = SIGNAL_ICONS.get(overall_sig, '🔵')

    fetched_at = data_json.get('fetched_at', '')
    if fetched_at:
        try:
            ft = datetime.fromisoformat(fetched_at)
            fetched_str = ft.strftime('%Y-%m-%d %H:%M')
        except:
            fetched_str = fetched_at
    else:
        fetched_str = '未知'

    # 信号面板
    signal_panel = f'''
    <div class="signal-panel">
      <div class="signal-card">
        <div class="signal-label">当前状态</div>
        <div class="signal-value {sig_cls}">{sig_icon}</div>
        <div class="signal-desc">{sig_msg}</div>
      </div>
      <div class="signal-card">
        <div class="signal-label">关联标的</div>
        <div class="signal-value" style="font-size:1.15rem;color:var(--text-primary)">{len(data_json.get('stocks', []))} 只股票</div>
        <div class="signal-desc">{'、'.join([s["name"] for s in sector.get("stocks", [])])}</div>
      </div>
      <div class="signal-card">
        <div class="signal-label">数据更新</div>
        <div class="signal-value" style="font-size:1rem;color:var(--text-primary)">{fetched_str}</div>
        <div class="signal-desc">每个交易日收盘后自动更新</div>
      </div>
    </div>'''

    # 指标卡片
    indicators = data_json.get('indicators', sector.get('indicators', []))
    ind_cards = ''
    for idx, ind in enumerate(indicators):
        ind_cards += generate_indicator_card(ind, idx)

    # 图表
    charts = generate_chart_section(data_json, sector['name'])

    # 股票明细表格
    stocks_html = ''
    stocks_data = data_json.get('stocks', [])
    if stocks_data:
        rows = ''
        for sd in stocks_data:
            change_cls = 'up' if (sd.get('change_pct') or 0) > 0 else ('down' if (sd.get('change_pct') or 0) < 0 else '')
            change_color = 'color:' + ('var(--up-color)' if change_cls == 'up' else ('var(--down-color)' if change_cls == 'down' else 'var(--text-primary)'))
            rows += f'''
            <tr>
              <td><b>{sd.get('name','')}</b></td>
              <td style="font-family:monospace">{sd.get('code','')}</td>
              <td style="font-weight:600;font-variant-numeric:tabular-nums">{sd.get('price','--')}</td>
              <td style="{change_color};font-weight:600;font-variant-numeric:tabular-nums">{'+' if (sd.get('change_pct') or 0) > 0 else ''}{sd.get('change_pct','--')}%</td>
              <td style="font-variant-numeric:tabular-nums">{format_value(sd.get('pe_ttm'))}</td>
              <td style="font-variant-numeric:tabular-nums">{format_value(sd.get('pb'))}</td>
            </tr>'''

        stocks_html = f'''
    <div class="section-label"><span class="icon">📋</span> 个股明细</div>
    <div style="overflow-x:auto;border-radius:var(--radius-md);border:1px solid var(--border-color)">
      <table style="margin:0;white-space:nowrap">
        <thead>
          <tr>
            <th>名称</th><th>代码</th><th>最新价</th><th>涨跌幅</th><th>PE(TTM)</th><th>PB</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>'''

    # 逻辑文章
    article_content = md_to_html(sector.get('logic_article', ''))

    page = HTML_HEADER.format(
        title=f"{sector['name']} - {site_name}",
        suffix=f' | {site_name}',
        description=sector.get('description', ''),
        css_path=css_rel,
    )
    page += NAVBAR.format(home_url='../index.html')
    page += f'''
<main class="container">

  <div class="breadcrumb">
    <a href="../index.html">首页</a>
    <span class="separator">›</span>
    <span>{html_escape(sector['name'])}</span>
  </div>

  <div class="detail-header">
    <div class="detail-title-group">
      <h1>{html_escape(sector['name'])}</h1>
      <div class="detail-meta">
        <span class="card-tag">{html_escape(sector.get('tag',''))}</span>
        <span>最后更新: {fetched_str}</span>
      </div>
    </div>
    <div class="detail-actions">
      <button id="shareBtn" class="btn">📤 分享</button>
    </div>
  </div>

  <!-- 信号面板 -->
  <div class="data-dashboard">
    <div class="section-label"><span class="icon">🚦</span> 当前状态</div>
    {signal_panel}
  </div>

  <!-- 指标看板 -->
  <div class="data-dashboard">
    <div class="section-label"><span class="icon">📊</span> 关键指标</div>
    <div class="indicator-grid">
      {ind_cards}
    </div>
  </div>

  <!-- 走势图 -->
  <div class="data-dashboard">
    {charts}
  </div>

  <!-- 个股明细 -->
  <div class="data-dashboard">
    {stocks_html}
  </div>

  <!-- 逻辑文章 -->
  <div class="article-section">
    <h2>📝 投资逻辑详解</h2>
    {article_content}
  </div>

</main>
'''
    page += FOOTER.format(
        footer_text=f'© {datetime.now().year} {site_name} | 数据仅供参考',
        js_path=js_rel,
    )

    return page, 200


# =====================================================
# 主流程
# =====================================================

args = None  # 全局变量，用于路径引用


def main():
    print('⚠️  注意: 此脚本为 v1 遗留代码，生成的页面格式可能与当前手动维护的首页不一致。')
    print('    如需生成板块详情页，请手动调用 generate_detail_page() 函数。')
    print('    当前网站首页请直接在根目录编辑 index.html。\n')
    
    global args
    parser = argparse.ArgumentParser(description='生成投资监控网站')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('--data', default='data/', help='数据目录')
    parser.add_argument('--output', default='output', help='输出目录')
    args = parser.parse_args()

    config_path = args.config
    data_dir = args.data
    output_dir = Path(args.output)

    # 加载配置
    config = load_config(config_path)

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'stocks').mkdir(parents=True, exist_ok=True)

    # 复制CSS和JS到输出目录
    templates_dir = Path(__file__).parent / 'templates'
    css_src = templates_dir / 'style.css'
    js_src = templates_dir / 'app.js'

    css_out = output_dir / 'style.css'
    js_out = output_dir / 'app.js'

    css_out.write_text(read_file(css_src), encoding='utf-8')
    js_out.write_text(read_file(js_src), encoding='utf-8')

    css_rel = 'style.css'
    js_rel = 'app.js'

    # 加载数据索引
    index_file = Path(data_dir) / 'index.json'
    if index_file.exists():
        with open(index_file, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
    else:
        index_data = {'updated_at': '', 'sectors': []}

    # 生成首页
    print('🏠 生成首页...')
    homepage = generate_homepage(config, index_data, css_rel, js_rel)
    (output_dir / 'index.html').write_text(homepage, encoding='utf-8')
    print(f'  ✅ index.html')

    # 生成各板块详情页
    sectors = config.get('sectors', [])
    for sector in sectors:
        sid = sector['id']
        print(f'📄 生成详情页: {sector["name"]} ({sid})...')
        detail, status = generate_detail_page(config, sid, '../' + css_rel, '../' + js_rel)
        detail_file = output_dir / 'stocks' / f'{sid}.html'
        detail_file.write_text(detail, encoding='utf-8')
        print(f'  ✅ stocks/{sid}.html')

    print(f'\n{"="*50}')
    print(f'🎉 网站生成完成！')
    print(f'📁 输出目录: {output_dir.resolve()}')
    print(f'🌐 首页: {(output_dir / "index.html").resolve()}')
    print(f'{"="*50}\n')


def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


if __name__ == '__main__':
    main()
