// ============================================
// 投资逻辑监控网站 - 前端交互
// 功能：搜索、标签筛选、暗色模式、图表、卡片点击、动态数据加载
// ============================================

(function () {
  'use strict';

  // --- 工具函数 ---
  var $ = function (sel, ctx) {
    return (ctx || document).querySelector(sel);
  };
  var $$ = function (sel, ctx) {
    return [].slice.call((ctx || document).querySelectorAll(sel));
  };

  // --- 动态数据加载 ---
  var DATA_BASE = (function () {
    // 自动检测 data/ 目录的基础路径
    var path = window.location.pathname;
    if (path.indexOf('/stocks/') !== -1 || path.indexOf('/reports/') !== -1) {
      return '../data/';
    }
    return 'data/';
  })();

  /** 从 data/*.json 加载并渲染到页面上 */
  function loadDashboardData() {
    // 1. 加载 index.json 获取更新时间
    fetch(DATA_BASE + 'index.json', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (idx) {
        renderUpdateTime(idx.updated_at);
      })
      .catch(function () { /* 离线时静默 */ });

    // 2. 找出所有带 data-sector-id 的容器，逐个加载对应 JSON
    var containers = $$('[data-sector-id]');
    containers.forEach(function (container) {
      var sid = container.dataset.sectorId;
      if (!sid) return;
      fetch(DATA_BASE + sid + '.json', { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (data) { renderSectorData(container, data); })
        .catch(function () { /* 离线时保留 HTML 写死的值 */ });
    });

    // 3. 如果是详情页（有 detail-page 标记），用 URL 推断 sector_id
    var detailPage = $('.detail-page');
    if (detailPage && !detailPage.dataset.sectorId) {
      var path = window.location.pathname;
      var match = path.match(/\/stocks\/(\w+)\.html/);
      if (match) {
        var inferredId = match[1];
        fetch(DATA_BASE + inferredId + '.json', { cache: 'no-store' })
          .then(function (r) { return r.json(); })
          .then(function (data) { renderDetailPage(data); })
          .catch(function () {});
      }
    } else if (detailPage && detailPage.dataset.sectorId) {
      fetch(DATA_BASE + detailPage.dataset.sectorId + '.json', { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (data) { renderDetailPage(data); })
        .catch(function () {});
    }
  }

  /** 渲染最后更新时间 */
  function renderUpdateTime(isoStr) {
    try {
      var d = new Date(isoStr);
      var fmt = d.getFullYear() + '-' +
                String(d.getMonth() + 1).padStart(2, '0') + '-' +
                String(d.getDate()).padStart(2, '0') + ' ' +
                String(d.getHours()).padStart(2, '0') + ':' +
                String(d.getMinutes()).padStart(2, '0');
      var els = $$('.last-update-time');
      els.forEach(function (el) { el.textContent = fmt; });
      // 也更新 header 区域的 last-update
      var headerUpdate = $('.last-update span:not(.dot)');
      if (headerUpdate) headerUpdate.textContent = '最后更新：' + fmt;
    } catch (e) {}
  }

  /** 将 JSON 数据渲染到首页 sector-card 上 */
  function renderSectorData(card, data) {
    if (!data || !data.stocks) return;

    // 更新信号徽章
    var badge = $('.signal-badge', card);
    if (badge && data.overall_signal) {
      badge.className = 'signal-badge ' + (data.overall_signal || 'warning');
      badge.textContent = data.signal_message || '';
    }

    // 更新各指标 mini-indicator 值
    if (data.indicators) {
      data.indicators.forEach(function (ind) {
        var key = ind.key;
        // 找对应的 mini-indicator
        $$('.mini-indicator', card).forEach(function (mi) {
          var label = ($('.label', mi) || {}).textContent || '';
          if (label.trim() === ind.name) {
            var valEl = $('.value', mi);
            if (valEl && ind.current_value != null) {
              var v = ind.current_value;
              var unit = ind.unit || '';
              if (unit === '%' || key === 'profit_growth' || key === 'roe' || key === 'price_vs_ma20') {
                valEl.textContent = v.toFixed(2) + '%';
              } else {
                valEl.textContent = v.toFixed(2);
              }

              // 根据信号变色
              valEl.className = 'value';
              if (ind.signal === 'good') valEl.classList.add('good');
              else if (ind.signal === 'bad') valEl.classList.add('bad');
            }
          }
        });
      });
    }

    // 更新个股明细（如果卡片内有 stock-prices 区域）
    if (data.stocks.length > 0) {
      updateStockChips(card, data.stocks);
    }
  }

  /** 更新股票 chip 显示最新价和涨跌 */
  function updateStockChips(card, stocks) {
    $$('.stock-chip', card).forEach(function (chip) {
      var name = chip.textContent.trim();
      var match = stocks.find(function (s) { return s.name === name; });
      if (!match) return;

      var price = match.price;
      var change = match.change_pct;
      var colorStyle = '';
      if (change > 0) colorStyle = 'color:var(--up-color)';
      else if (change < 0) colorStyle = 'color:var(--down-color)';

      chip.innerHTML = '<b>' + name + '</b> ' +
        '<span style="font-weight:600;' + colorStyle + '">' + price.toFixed(2) + '</span>' +
        '<span style="font-size:11px;' + colorStyle + '">(' + (change >= 0 ? '+' : '') + change.toFixed(2) + '%)</span>';
    });
  }

  /** 将 JSON 数据渲染到详情页（stocks/*.html） */
  function renderDetailPage(data) {
    if (!data) return;

    var page = document.body;  // 整个 body 作为上下文

    // 1. 更新时间戳
    renderUpdateTime(data.fetched_at);

    // 2. 更新信号面板
    if (data.overall_signal) {
      var sigVal = $('.signal-value', page);
      if (sigVal) {
        sigVal.className = 'signal-value ' + (data.overall_signal || 'warning');
        if (data.overall_signal === 'safe') sigVal.textContent = '\u2705';
        else if (data.overall_signal === 'danger') sigVal.textContent = '\u26A0\uFE0F';
        else sigVal.textContent = '\U0001F7E1';
      }
      var sigDesc = $('.signal-desc', page);
      if (sigDesc) sigDesc.textContent = data.signal_message || '';
    }

    // 3. 更新关联标的数量
    if (data.stocks) {
      var countVal = $$('.signal-card .signal-value')[1];
      if (countVal) countVal.textContent = data.stocks.length + ' \u53EA\u80A1\u7968';
      var countDesc = $$('.signal-card .signal-desc')[1];
      if (countDesc) {
        countDesc.textContent = data.stocks.map(function (s) { return s.name; }).join('\u3001');
      }
    }

    // 4. 更新指标看板
    if (data.indicators) {
      data.indicators.forEach(function (ind) {
        // 找 indicator-card by ind-name
        $$('.indicator-card', page).forEach(function (ic) {
          var nameEl = ($('.ind-name', ic) || {}).textContent || '';
          if (nameEl.trim() === ind.name) {
            var valEl = ($('.ind-value', ic) || {});
            if (valEl && ind.current_value != null) {
              var v = ind.current_value;
              var unit = ind.unit || '';
              if (unit === '%') valEl.textContent = v.toFixed(2) + '%';
              else valEl.textContent = v.toFixed(2);

              // 进度条
              var barFill = ($('.ind-bar-fill', ic) || {});
              if (barFill && ind.threshold_low != null && ind.threshold_high != null) {
                var range = ind.threshold_high - ind.threshold_low;
                var pct = ((v - ind.threshold_low) / range) * 100;
                pct = Math.max(0, Math.min(100, pct));
                barFill.style.width = pct + '%';
                barFill.className = 'ind-bar-fill ' + (ind.signal || 'warn');
              }

              // 值颜色
              valEl.className = 'ind-value';
              if (ind.signal === 'good') valEl.classList.add('good');
              else if (ind.signal === 'bad') valEl.classList.add('bad');
            }
          }
        });
      });
    }

    // 5. 更新走势图（如果有 history 数据）
    if (data.stocks && data.stocks[0] && data.stocks[0].history) {
      var chartContainer = $('.chart-container[data-type="line"]', page);
      if (chartContainer) {
        var stock = data.stocks[0];  // 用第一只股票的历史数据
        var hist = stock.history || [];
        var labels = hist.map(function (h) {
          var d = h.date.split('-');
          return (d[1] || '') + '/' + (d[2] || '');
        });
        var points = hist.map(function (h) {
          return { date: h.date, value: h.close };
        });
        chartContainer.dataset.json = JSON.stringify({
          type: 'line',
          labels: labels,
          points: points,
          title: (stock.name || '') + ' \u80A2\u4EF7\u8D70\u52BF(120\u65E5)'
        });
        // 重新渲染该图表（清除旧的 canvas）
        var area = chartContainer.querySelector('.chart-canvas-area');
        if (area) area.innerHTML = '';
        renderSingleLineChart(chartContainer);
      }
    }

    // 6. 更新个股明细表格
    if (data.stocks) {
      var tbody = $('table tbody', page);
      if (tbody) {
        var rows = '';
        data.stocks.forEach(function (s) {
          var changeColor = s.change_pct > 0 ? 'color:var(--up-color)' : (s.change_pct < 0 ? 'color:var(--down-color)' : '');
          var changePrefix = s.change_pct >= 0 ? '+' : '';
          rows += '<tr>' +
            '<td><b>' + s.name + '</b></td>' +
            '<td style="font-family:monospace">' + s.code + '</td>' +
            '<td style="font-weight:600;font-variant-numeric:tabular-nums">' + (s.price || 0).toFixed(2) + '</td>' +
            '<td style="' + changeColor + ';font-weight:600;font-variant-numeric:tabular-nums">' + changePrefix + (s.change_pct || 0).toFixed(2) + '%</td>' +
            '<td style="font-variant-numeric:tabular-nums">' + ((s.pe_ttm || 0)).toFixed(2) + '</td>' +
            '<td style="font-variant-numeric:tabular-nums">' + ((s.pb || 0)).toFixed(2) + '</td>' +
            '</tr>';
        });
        tbody.innerHTML = rows;
      }
    }
  }

  /** 单独渲染一个折线图（用于详情页动态更新） */
  function renderSingleLineChart(container) {
    var chartType = container.dataset.type;
    var dataStr = container.dataset.json;
    if (!dataStr) return;
    try {
      var data = JSON.parse(dataStr);
      if (chartType === 'line') renderLineChart(container, data);
    } catch (e) {
      console.error('\u56FE\u8868\u6570\u636E\u89E3\u6790\u5931\u8D25:', e);
    }
  }

  // --- 暗色模式 ---
  function initTheme() {
    var saved = localStorage.getItem('theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var theme = saved || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcon(theme);
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') || 'light';
    var next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateThemeIcon(next);
  }

  function updateThemeIcon(theme) {
    var btn = $('.theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
  }

  // --- 卡片点击跳转 ---
  function initCardClicks() {
    $$('.sector-card').forEach(function (card) {
      card.style.cursor = 'pointer';
      card.addEventListener('click', function (e) {
        // 点击交互元素时不跳转
        var tag = e.target.tagName.toLowerCase();
        if (tag === 'input' || tag === 'button' || tag === 'a' || tag === 'select') return;
        if (e.target.closest('.search-wrapper')) return;
        if (e.target.closest('.tag-btn')) return;

        var href = card.dataset.href;
        if (href) {
          window.location.href = href;
        }
      });
    });
  }

  // --- 搜索功能（支持板块内部信息：股票名/代码、指标名、逻辑文章关键词） ---
  function initSearch() {
    var input = $('.search-input');
    if (!input) return;

    input.addEventListener('input', function () {
      var query = this.value.trim().toLowerCase();
      $$('.sector-card').forEach(function (card) {
        // 优先使用 data-search-text（包含完整可搜索内容）
        var searchText = card.dataset.searchText || '';
        // 兜底：从卡片可见元素取文本
        var name = ($('.card-title', card) || {}).textContent || '';
        var desc = ($('.card-desc', card) || {}).textContent || '';
        var tag = ($('.card-tag', card) || {}).textContent || '';
        var chips = $$('.stock-chip', card).map(function (el) { return el.textContent; }).join(' ');
        var allText = searchText + ' ' + name + ' ' + desc + ' ' + tag + ' ' + chips;

        var match = !query || allText.toLowerCase().indexOf(query) !== -1;
        card.style.display = match ? '' : 'none';
      });

      var visible = $$('.sector-card').filter(function (c) { return c.style.display !== 'none'; });
      var noResult = $('.no-results');
      if (!noResult && query && visible.length === 0) {
        noResult = document.createElement('div');
        noResult.className = 'no-results';
        noResult.innerHTML = '<div class="emoji">\uD83D\uDD0D</div><p>\u6CA1\u6709\u627E\u5230\u5339\u914D\u7684\u677F\u5757</p><p style="font-size:13px;color:var(--text-muted);margin-top:4px">\u8BD5\u8BD5\u641C\u80A1\u7968\u4EE3\u7801\u3001\u6307\u6807\u540D\u79F0\u6216\u903B\u8F91\u5173\u952E\u8BCD</p>';
        var grid = $('.sector-grid');
        if (grid) grid.appendChild(noResult);
      } else if (noResult && (visible.length > 0 || !query)) {
        noResult.remove();
      }
    });
  }

  // --- 标签筛选 ---
  function initTagFilter() {
    $$('.tag-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        $$('.tag-btn').forEach(function (b) { b.classList.remove('active'); });
        this.classList.add('active');
        var tag = this.dataset.tag;
        $$('.sector-card').forEach(function (card) {
          if (!tag || tag === 'all') {
            card.style.display = '';
          } else {
            var cardTag = ($('.card-tag', card) || {}).textContent || '';
            card.style.display = cardTag.trim() === tag ? '' : 'none';
          }
        });
      });
    });
  }

  // --- 图表渲染 ---
  function renderCharts() {
    $$('.chart-container').forEach(function (container) {
      var chartType = container.dataset.type;
      var dataStr = container.dataset.json;
      if (!dataStr) return;
      try {
        var data = JSON.parse(dataStr);
        if (chartType === 'line') renderLineChart(container, data);
      } catch (e) {
        console.error('\u56FE\u8868\u6570\u636E\u89E3\u6790\u5931\u8D25:', e);
      }
    });
  }

  function getComputedColor(varName) {
    return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  }

  function renderLineChart(container, data) {
    var canvas = document.createElement('canvas');
    var area = container.querySelector('.chart-canvas-area');
    if (!area) return;
    area.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    var rect = container.getBoundingClientRect();
    var dpr = window.devicePixelRatio || 1;
    var W = Math.max(rect.width - 40, 200);
    var H = 300;
    var pad = { t: 20, r: 20, b: 36, l: 52 };

    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.scale(dpr, dpr);

    var points = data.points || [];
    var labels = data.labels || [];
    var values = points.map(function (p) { return p.value; });
    var minV = Math.min.apply(null, values) * 0.98;
    var maxV = Math.max.apply(null, values) * 1.02;
    var range = maxV - minV || 1;

    var theme = document.documentElement.getAttribute('data-theme') || 'light';

    // 背景
    ctx.fillStyle = getComputedColor('--bg-card') || '#fff';
    ctx.fillRect(0, 0, W, H);

    // 网格线
    ctx.strokeStyle = getComputedColor('--border-color') || '#e0e0e0';
    ctx.lineWidth = 0.5;
    for (var i = 0; i <= 4; i++) {
      var y = pad.t + (H - pad.t - pad.b) * i / 4;
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(W - pad.r, y);
      ctx.stroke();

      var val = maxV - (range * i / 4);
      ctx.fillStyle = getComputedColor('--text-muted') || '#999';
      ctx.font = '11px SF Mono, Consolas, monospace';
      ctx.textAlign = 'right';
      ctx.fillText(val.toFixed(2), pad.l - 8, y + 4);
    }

    if (points.length > 1) {
      var upColor = getComputedColor('--up-color') || '#e53935';
      var textColor = getComputedColor('--text-primary') || '#1a1a2e';

      var coords = points.map(function (p, i) {
        return {
          x: pad.l + (W - pad.l - pad.r) * (i / Math.max(points.length - 1, 1)),
          y: pad.t + (H - pad.t - pad.b) * (1 - (p.value - minV) / range),
          value: p.value
        };
      });

      // 渐变填充
      var gradient = ctx.createLinearGradient(0, pad.t, 0, H - pad.b);
      gradient.addColorStop(0, upColor + '40');
      gradient.addColorStop(1, upColor + '00');

      ctx.beginPath();
      ctx.moveTo(coords[0].x, H - pad.b);
      coords.forEach(function (c) { ctx.lineTo(c.x, c.y); });
      ctx.lineTo(coords[coords.length - 1].x, H - pad.b);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();

      // 折线
      ctx.beginPath();
      coords.forEach(function (c, i) {
        if (i === 0) ctx.moveTo(c.x, c.y);
        else ctx.lineTo(c.x, c.y);
      });
      ctx.strokeStyle = upColor;
      ctx.lineWidth = 2;
      ctx.stroke();

      // 最新点
      var last = coords[coords.length - 1];
      ctx.beginPath();
      ctx.arc(last.x, last.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = upColor;
      ctx.fill();
      ctx.strokeStyle = theme === 'dark' ? '#1c2128' : '#ffffff';
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = textColor;
      ctx.font = 'bold 12px SF Mono, Consolas, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(last.value.toFixed(2), last.x + 10, last.y - 6);
    }

    // X轴标签
    ctx.fillStyle = getComputedColor('--text-muted') || '#999';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    var step = Math.ceil(labels.length / 6);
    labels.forEach(function (label, i) {
      if (i % step === 0 || i === labels.length - 1) {
        var x = pad.l + (W - pad.l - pad.r) * (i / Math.max(labels.length - 1, 1));
        ctx.fillText(label, x, H - pad.b + 18);
      }
    });
  }

  // --- 图表Tab切换 ---
  function initChartTabs() {
    $$('.chart-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        var parent = this.closest('.chart-container');
        if (!parent) return;
        $$('.chart-tab', parent).forEach(function (t) { t.classList.remove('active'); });
        this.classList.add('active');
        var targetId = this.dataset.target;
        $$('.chart-panel', parent).forEach(function (panel) {
          panel.style.display = panel.id === targetId ? '' : 'none';
        });
      });
    });
  }

  // --- 分享功能 ---
  function initShare() {
    var shareBtn = $('#shareBtn');
    if (!shareBtn) return;
    shareBtn.addEventListener('click', async function () {
      var url = window.location.href;
      if (navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(url);
          shareBtn.textContent = '\u2705 \u5DF2\u590D\u5236\u94FE\u63A5';
          setTimeout(function () { shareBtn.innerHTML = '\uD83D\uDCC4 \u5206\u4EAB'; }, 2000);
        } catch (e) {}
      }
    });
  }

  // --- 初始化 ---
  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    var themeToggle = $('.theme-toggle');
    if (themeToggle) themeToggle.addEventListener('click', toggleTheme);
    initSearch();
    initTagFilter();
    initChartTabs();
    renderCharts();
    initShare();
    initCardClicks();
    // 动态加载 JSON 数据
    loadDashboardData();
  });

})();
