var oppData = window.__TAOLI_DATA__ || [];
var scanState = window.__TAOLI_SCAN_STATE__ || {};
var openDetailIds = new Set();
var refreshPaused = false;

function renderAll() {
    updateCounts();
    if (oppData.length) {
        ensureTable();
        rebuildTableRows();
    } else {
        updateTable();
    }
}

function updateCounts() {
    var types = {put_call_parity:0, box_spread:0, implied_futures_basis:0}, pcpModes={same_exchange:0, cross_exchange:0}, exec=0;
    oppData.forEach(function(o) {
        if (types[o.type] !== undefined) types[o.type]++;
        if (o.type === 'put_call_parity' && pcpModes[o.pcp_execution_mode] !== undefined) pcpModes[o.pcp_execution_mode]++;
        if (o.executable) exec++;
    });
    document.querySelectorAll('.pill').forEach(function(p) {
        var t = p.dataset.type;
        var m = p.dataset.pcpMode;
        var span = p.querySelector('.count');
        if (span && t) span.textContent = types[t] || 0;
        if (span && m) span.textContent = pcpModes[m] || 0;
    });
    document.getElementById('stat-total').textContent = oppData.length;
    document.getElementById('stat-exec').textContent = exec;
    document.querySelectorAll('[data-stat-type]').forEach(function(el) {
        el.textContent = types[el.dataset.statType] || 0;
    });
    updatePcpMenuState();
}

function toggleFilter(pill) {
    pill.classList.toggle('on');
    pill.setAttribute('aria-pressed', pill.classList.contains('on') ? 'true' : 'false');
    updatePcpMenuState();
    updateTable();
}

function updateTable() {
    var active = new Set();
    var activePcpModes = new Set();
    var activeExchanges = new Set();
    var visibleTypes = {put_call_parity:0, box_spread:0, implied_futures_basis:0};
    var visiblePcpModes = {same_exchange:0, cross_exchange:0};
    var visibleExec = 0;
    var visibleTotal = 0;
    document.querySelectorAll('.pill.on[data-type]').forEach(function(p) { active.add(p.dataset.type); });
    document.querySelectorAll('.pill.on[data-pcp-mode]').forEach(function(p) { activePcpModes.add(p.dataset.pcpMode); });
    document.querySelectorAll('#exchange-filter input[data-exchange]:checked').forEach(function(input) {
        activeExchanges.add(input.dataset.exchange);
    });
    var tbody = document.getElementById('opp-tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr.data-row'));
    rows.forEach(function(r) {
        var show = active.has(r.dataset.type);
        if (show && r.dataset.type === 'put_call_parity') show = activePcpModes.has(r.dataset.pcpMode);
        if (show) show = rowMatchesSelectedExchange(r, activeExchanges);
        r.style.display = show ? '' : 'none';
        if (show) {
            visibleTotal++;
            if (visibleTypes[r.dataset.type] !== undefined) visibleTypes[r.dataset.type]++;
            if (r.dataset.type === 'put_call_parity' && visiblePcpModes[r.dataset.pcpMode] !== undefined) visiblePcpModes[r.dataset.pcpMode]++;
            if (r.classList.contains('exec')) visibleExec++;
        }
    });
    updateVisibleCounts(visibleTypes, visiblePcpModes, visibleExec, visibleTotal);
}

function updateVisibleCounts(types, pcpModes, exec, total) {
    document.querySelectorAll('.pill').forEach(function(p) {
        var t = p.dataset.type;
        var m = p.dataset.pcpMode;
        var span = p.querySelector('.count');
        if (span && t) span.textContent = types[t] || 0;
        if (span && m) span.textContent = pcpModes[m] || 0;
    });
    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-exec').textContent = exec;
    document.querySelectorAll('[data-stat-type]').forEach(function(el) {
        el.textContent = types[el.dataset.statType] || 0;
    });
}

function rowMatchesSelectedExchange(row, activeExchanges) {
    if (!activeExchanges.size) return true;
    var rowExchange = row.dataset.exchange || '';
    var rowId = row.dataset.id || '';
    var matched = false;
    activeExchanges.forEach(function(exchange) {
        if (rowExchange === exchange || rowId.indexOf(exchange + ':') >= 0) matched = true;
    });
    return matched;
}

function updatePcpMenuState() {
    var group = document.querySelector('.pcp-filter');
    var pcp = document.querySelector('.pill[data-type="put_call_parity"]');
    if (!group || !pcp) return;
    group.classList.toggle('pcp-off', !pcp.classList.contains('on'));
}

function toggleDetail(id, trigger) {
    var dr = document.getElementById('detail-' + id);
    if (!dr) return;
    dr.classList.toggle('open');
    var isOpen = dr.classList.contains('open');
    if (isOpen) openDetailIds.add(id);
    else openDetailIds.delete(id);
    if (trigger) trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
}

function scanLive() {
    var bar = document.getElementById('scanning-bar');
    var btn = document.getElementById('btn-scan');
    var err = document.getElementById('err-bar');
    var progress = document.getElementById('progress-log');
    bar.classList.add('show');
    progress.classList.add('show');
    updateProgress(['提交扫描请求...']);
    err.classList.remove('show');
    btn.disabled = true;
    btn.textContent = '提交扫描...';
    fetch('/api/scan?live=1&exchanges=' + encodeURIComponent(selectedExchangeParam())).then(function(r) { return r.json(); }).then(function(d) {
        btn.textContent = '后端扫描中...';
        pollForResults(0);
    }).catch(function(e) {
        bar.classList.remove('show');
        err.classList.add('show');
        document.getElementById('err-text').textContent = '无法连接后端扫描接口: ' + e;
        btn.disabled = false;
        btn.textContent = 'Scan live';
    });
}

function selectedExchangeParam() {
    var selected = [];
    document.querySelectorAll('#exchange-filter input[data-exchange]:checked').forEach(function(input) {
        selected.push(input.dataset.exchange);
    });
    if (!selected.length) selected = ['deribit', 'binance', 'okx', 'bybit', 'gate'];
    return selected.join(',');
}

function pollForResults(attempt) {
    if (attempt > 180) {
        document.getElementById('scanning-bar').classList.remove('show');
        document.getElementById('err-bar').classList.add('show');
        document.getElementById('err-text').textContent = '后端扫描仍未返回结果，请查看服务器日志。';
        document.getElementById('btn-scan').textContent = 'Scan live';
        document.getElementById('btn-scan').disabled = false;
        return;
    }
    fetch('/api/scan?cache=1').then(function(r) { return r.json(); }).then(function(d) {
        updateProgress(d.progress || []);
        if (d.opportunities && d.opportunities.length) {
            applyScanData(d);
        }
        if (d.scanning) {
            document.getElementById('btn-scan').textContent = '后端扫描中...';
            setTimeout(function() { pollForResults(attempt+1); }, 2000);
        } else if (d.error) {
            document.getElementById('scanning-bar').classList.remove('show');
            document.getElementById('err-bar').classList.add('show');
            document.getElementById('err-text').textContent = d.error;
            document.getElementById('btn-scan').textContent = 'Scan live';
            document.getElementById('btn-scan').disabled = false;
        } else if (d.total > 0 || (d.scanned_at && d.scanned_at !== '—')) {
            document.getElementById('scanning-bar').classList.remove('show');
            document.getElementById('btn-scan').textContent = 'Scan live';
            document.getElementById('btn-scan').disabled = false;
            if (d.opportunities && d.opportunities.length) applyScanData(d);
        } else {
            document.getElementById('scanning-bar').classList.remove('show');
            document.getElementById('err-bar').classList.add('show');
            document.getElementById('err-text').textContent = '后端暂无扫描结果，请重新点击实盘扫描。';
            document.getElementById('btn-scan').textContent = 'Scan live';
            document.getElementById('btn-scan').disabled = false;
        }
    }).catch(function(e) {
        document.getElementById('scanning-bar').classList.remove('show');
        document.getElementById('err-bar').classList.add('show');
        document.getElementById('err-text').textContent = '读取后端扫描状态失败: ' + e;
        document.getElementById('btn-scan').textContent = 'Scan live';
        document.getElementById('btn-scan').disabled = false;
    });
}

function applyScanData(d) {
    oppData = d.opportunities || [];
    ensureTable();
    sortOppData(sortCol, sortAsc);
    rebuildTableRows();
    updateCounts();
    document.getElementById('stat-total').textContent = String(d.total || oppData.length);
    var execCount = 0;
    oppData.forEach(function(o) { if (o.executable) execCount++; });
    document.getElementById('stat-exec').textContent = String((d.stats && d.stats.executable) || execCount);
    if (d.scanned_at) document.getElementById('scan-time').textContent = d.scanned_at + (d.partial ? ' · partial' : '');
    var badge = document.getElementById('status-badge');
    if (badge) {
        badge.className = 'badge ' + (d.error ? 'badge-err' : 'badge-live');
        badge.textContent = d.partial ? 'PARTIAL' : 'LIVE';
    }
    updateTable();
}

function ensureTable() {
    if (document.getElementById('opp-tbody')) return;
    var wrap = document.querySelector('.table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<table><thead><tr>' +
        '<th data-col="exchange" style="width:60px"><button type="button" class="sort-btn">交易所<span class="ar"></span></button></th>' +
        '<th data-col="type" style="width:48px"><button type="button" class="sort-btn">类型<span class="ar"></span></button></th>' +
        '<th data-col="expiry_ms" style="width:90px"><button type="button" class="sort-btn">行权日<span class="ar"></span></button></th>' +
        '<th data-col="strike_display" style="width:90px"><button type="button" class="sort-btn">行权价<span class="ar"></span></button></th>' +
        '<th data-col="gross_profit" style="width:90px"><button type="button" class="sort-btn">收益<span class="ar"></span></button></th>' +
        '<th data-col="annualized_return" class="sorted" aria-sort="descending" style="width:80px"><button type="button" class="sort-btn">年化<span class="ar">desc</span></button></th>' +
        '<th data-col="capital" style="width:80px"><button type="button" class="sort-btn">占用<span class="ar"></span></button></th>' +
        '<th style="width:auto">风险<span class="ar"></span></th>' +
        '</tr></thead><tbody id="opp-tbody"></tbody></table>';
    bindSortHeaders();
}

function updateProgress(lines) {
    var progress = document.getElementById('progress-log');
    var stage = document.getElementById('scan-stage');
    if (!progress) return;
    if (!lines || !lines.length) lines = ['等待后端状态...'];
    progress.textContent = lines.join('\\n');
    progress.scrollTop = progress.scrollHeight;
    if (stage) stage.textContent = lines[lines.length - 1];
}

document.querySelectorAll('[data-scan-button]').forEach(function(btn) {
    btn.addEventListener('click', function(ev) {
        ev.preventDefault();
        scanLive();
    });
});
document.querySelectorAll('.pill').forEach(function(pill) {
    pill.addEventListener('click', function() { toggleFilter(pill); });
});
document.querySelectorAll('#exchange-filter input[data-exchange]').forEach(function(input) {
    input.addEventListener('change', updateTable);
});
var manualScan = document.getElementById('manual-scan');
if (manualScan) {
    manualScan.addEventListener('click', function(ev) {
        ev.preventDefault();
        scanLive();
    });
}
var refreshToggle = document.getElementById('refresh-toggle');
if (refreshToggle) {
    refreshToggle.addEventListener('click', function() {
        refreshPaused = !refreshPaused;
        refreshToggle.setAttribute('aria-pressed', refreshPaused ? 'true' : 'false');
        refreshToggle.textContent = refreshPaused ? '继续刷新' : '暂停刷新';
        if (refreshPaused) {
            document.getElementById('refresh-timer').textContent = 'paused';
        } else {
            _countdown = REFRESH_SECONDS;
            document.getElementById('refresh-timer').textContent = _countdown + 's';
        }
    });
}

function resumeScanIfNeeded() {
    if (!scanState || !scanState.scanning) return;
    document.getElementById('scanning-bar').classList.add('show');
    document.getElementById('progress-log').classList.add('show');
    document.getElementById('btn-scan').disabled = true;
    document.getElementById('btn-scan').textContent = '后端扫描中...';
    updateProgress(scanState.progress || ['后端扫描中...']);
    pollForResults(0);
}

var sortCol = 'annualized_return', sortAsc = false;
function bindSortHeaders() {
    document.querySelectorAll('thead th[data-col]').forEach(function(th) {
        var button = th.querySelector('.sort-btn') || th;
        if (button.dataset.boundSort === '1') return;
        button.dataset.boundSort = '1';
        button.addEventListener('click', function() {
            var col = th.dataset.col;
            if (sortCol === col) sortAsc = !sortAsc;
            else { sortCol = col; sortAsc = false; }
            sortTable(col, sortAsc);
            document.querySelectorAll('thead th').forEach(function(h) {
                h.classList.remove('sorted');
                h.removeAttribute('aria-sort');
                var ar = h.querySelector('.ar');
                if (ar) ar.textContent = '';
            });
            th.classList.add('sorted');
            th.setAttribute('aria-sort', sortAsc ? 'ascending' : 'descending');
            var ar = th.querySelector('.ar');
            if (ar) ar.textContent = sortAsc ? 'asc' : 'desc';
        });
    });
}

function sortTable(col, asc) {
    sortOppData(col, asc);
    renderAll();
}

function sortOppData(col, asc) {
    oppData.sort(function(a, b) {
        var va = sortValue(a, col), vb = sortValue(b, col);
        if (va === null || va === undefined) va = '';
        if (vb === null || vb === undefined) vb = '';
        if (typeof va === 'number' && typeof vb === 'number') {
            return asc ? va - vb : vb - va;
        }
        va = String(va); vb = String(vb);
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
    });
}

function sortValue(o, col) {
    if (col === 'strike_display') return displayStrike(o);
    if (col === 'gross_profit' || col === 'annualized_return' || col === 'capital' || col === 'expiry_ms') {
        var n = parseFloat(o[col]);
        return isNaN(n) ? null : n;
    }
    return o[col];
}

function rebuildTableRows() {
    var tbody = document.getElementById('opp-tbody');
    tbody.innerHTML = oppData.map(function(o) { return renderRow(o) + renderDetail(o); }).join('');
    restoreOpenDetails();
    updateTable();
}

function restoreOpenDetails() {
    openDetailIds.forEach(function(id) {
        var row = document.getElementById('detail-' + id);
        if (row) {
            row.classList.add('open');
            var trigger = document.querySelector('[aria-controls="detail-' + CSS.escape(String(id)) + '"]');
            if (trigger) trigger.setAttribute('aria-expanded', 'true');
        }
        else openDetailIds.delete(id);
    });
}

function renderRow(o) {
    var labels = {put_call_parity:'PCP', box_spread:'Box', implied_futures_basis:'IFB'};
    var css = {put_call_parity:'pcp', box_spread:'box', implied_futures_basis:'ifb'};
    var s = displayStrike(o);
    var rt = (o.risk_tags || []).map(function(t) {
        t = String(t || '');
        var c = t.indexOf('inverse') >= 0 ? 'inv' : 'warn';
        return '<span class="'+c+'">' + esc(t.replace(/_/g, ' ')) + '</span>';
    }).join('');
    var id = domId(o.id || '');
    var type = esc(o.type || '');
    var pcpMode = esc(o.pcp_execution_mode || '');
    var label = esc(labels[o.type] || o.type || '');
    var typeClass = esc(css[o.type] || '');
    return '<tr class="data-row '+(o.executable?'exec':'noexec')+'" data-type="'+type+'" data-pcp-mode="'+pcpMode+'" data-exchange="'+esc(o.exchange || '')+'" data-id="'+id+'">'+
        '<td class="n">'+esc(o.exchange || '')+'</td>'+
        '<td class="ty '+typeClass+'"><button type="button" class="link-button detail-toggle" aria-expanded="'+(openDetailIds.has(id)?'true':'false')+'" aria-controls="detail-'+id+'" onclick="toggleDetail(&quot;'+id+'&quot;, this)">'+label+'</button></td>'+
        '<td class="n">'+tsToDate(o.expiry_ms)+'</td>'+
        '<td class="n">'+esc(s)+'</td>'+
        '<td class="n up">'+esc(fmtUSD(o.gross_profit))+'</td>'+
        '<td class="n rt">'+esc(fmtAPY(o.annualized_return))+'</td>'+
        '<td class="n ca">'+esc(fmtUSD(o.capital))+'</td>'+
        '<td><div class="rt">'+rt+'</div></td>'+
        '</tr>';
}

function renderDetail(o) {
    var legs = renderLegTable(o);
    var id = domId(o.id || '');
    return '<tr class="detail" id="detail-'+id+'"><td colspan="8">'+
        '<div class="dg">'+
        '<div><dt>交易所</dt><dd>'+o.exchange+'</dd></div>'+
        '<div><dt>标的</dt><dd>'+o.underlying+'</dd></div>'+
        '<div><dt>到期日</dt><dd>'+tsToDate(o.expiry_ms)+'</dd></div>'+
        '<div><dt>可执行</dt><dd style="color:var(--green)">'+(o.executable?'是':'否')+'</dd></div>'+
        '</div>'+
        '<div class="sim-head"><button class="sim-btn" onclick="simulatePayoff(&quot;'+id+'&quot;)">一键模拟</button><span class="payoff-note">到期价格 / 盈亏金额</span></div>'+
        '<div class="payoff-chart" id="payoff-chart-'+id+'"></div>'+
        legs+
        '</td></tr>';
}

function renderLegTable(o) {
    var rows = (o.legs || []).map(function(l, idx) {
        var instrument = parseInstrumentKey(l.instrument_key);
        var side = String(l.side || '');
        var action = side === 'buy' ? '买入' : (side === 'sell' ? '卖出' : side);
        var sideClass = side === 'buy' ? 'side-buy' : (side === 'sell' ? 'side-sell' : '');
        var strike = legStrike(o, l);
        return '<tr>'+
            '<td class="n">'+(idx + 1)+'</td>'+
            '<td><span class="leg-action '+sideClass+'">'+esc(action)+'</span></td>'+
            '<td>'+esc(instrument.exchange)+'</td>'+
            '<td>'+esc(instrument.market)+'</td>'+
            '<td title="'+esc(l.instrument_key || '')+'">'+esc(instrument.contract)+'</td>'+
            '<td>'+esc(tsToDate(o.expiry_ms))+'</td>'+
            '<td class="n">'+esc(strike)+'</td>'+
            '<td>'+esc(l.role || '')+'</td>'+
            '<td class="n">'+esc(l.price || '')+'</td>'+
            '<td class="n">'+esc(l.size || '')+'</td>'+
            '</tr>';
    }).join('');
    if (!rows) rows = '<tr><td colspan="10">无执行腿数据</td></tr>';
    return '<div class="dleg"><div class="dleg-title">执行腿</div><table><thead><tr>'+
        '<th>#</th><th>动作</th><th>交易所</th><th>市场</th><th>合约</th><th>到期日</th><th>行权价</th><th>角色</th><th>价格</th><th>数量</th>'+
        '</tr></thead><tbody>'+rows+'</tbody></table></div>';
}

function parseInstrumentKey(key) {
    var parts = String(key || '').split(':');
    return {
        exchange: parts[0] || '',
        market: parts[1] || '',
        contract: parts.slice(2).join(':') || String(key || '')
    };
}

function legStrike(o, l) {
    var instrument = parseInstrumentKey(l.instrument_key);
    var role = String(l.role || '');
    if (role.indexOf('lower_') === 0) return fmtStrike(o.lower_strike || '');
    if (role.indexOf('upper_') === 0) return fmtStrike(o.upper_strike || '');
    if (role === 'call' || role === 'put') return fmtStrike(o.strike || '');
    if (instrument && instrument.market === 'option') return fmtStrike(strikeFromContract(instrument.contract));
    return '';
}

function strikeFromContract(contract) {
    var parts = String(contract || '').split('-');
    for (var i = 0; i < parts.length; i++) {
        if (/^\\d+(\\.\\d+)?$/.test(parts[i])) return parts[i];
    }
    return '';
}

function displayStrike(o) {
    if (o.strike !== null && o.strike !== undefined && o.strike !== '') return fmtStrike(o.strike);
    if (o.lower_strike !== null && o.lower_strike !== undefined && o.upper_strike !== null && o.upper_strike !== undefined) {
        return fmtStrike(o.lower_strike) + '-' + fmtStrike(o.upper_strike);
    }
    return '';
}

function fmtStrike(v) {
    if (v === null || v === undefined || v === '') return '';
    var s = String(v);
    var d = Number(s);
    if (!isFinite(d)) return s;
    if (Math.abs(d - Math.round(d)) < 1e-9) return String(Math.round(d));
    return s.replace(/(\\.\\d*?[1-9])0+$/, '$1').replace(/\\.0+$/, '');
}

function simulatePayoff(id) {
    var o = null;
    for (var i = 0; i < oppData.length; i++) {
        if (domId(oppData[i].id) === String(id)) { o = oppData[i]; break; }
    }
    if (!o) return;
    var chart = document.getElementById('payoff-chart-' + id);
    if (!chart) return;
    chart.innerHTML = renderPayoffChart(o);
    chart.classList.add('show');
}

function renderPayoffChart(o) {
    var range = payoffPriceRange(o);
    var points = [];
    for (var i = 0; i <= 60; i++) {
        var price = range.min + (range.max - range.min) * i / 60;
        points.push({x: price, y: strategyPayoffAtExpiry(o, price)});
    }
    var minY = Math.min(0, Math.min.apply(null, points.map(function(p) { return p.y; })));
    var maxY = Math.max(0, Math.max.apply(null, points.map(function(p) { return p.y; })));
    if (maxY === minY) { maxY += 1; minY -= 1; }
    var w = 760, h = 280, pad = 38;
    function sx(x) { return pad + (x - range.min) / (range.max - range.min) * (w - pad * 2); }
    function sy(y) { return h - pad - (y - minY) / (maxY - minY) * (h - pad * 2); }
    var path = points.map(function(p, idx) { return (idx ? 'L' : 'M') + sx(p.x).toFixed(1) + ' ' + sy(p.y).toFixed(1); }).join(' ');
    var zeroY = sy(0);
    var midX = range.min + (range.max - range.min) / 2;
    return '<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="到期损益图">'+
        '<line x1="'+pad+'" y1="'+zeroY.toFixed(1)+'" x2="'+(w-pad)+'" y2="'+zeroY.toFixed(1)+'" stroke="#3a3a34" stroke-width="1"/>'+
        '<line x1="'+pad+'" y1="'+pad+'" x2="'+pad+'" y2="'+(h-pad)+'" stroke="#3a3a34" stroke-width="1"/>'+
        '<path d="'+path+'" fill="none" stroke="#ffb800" stroke-width="2.5"/>'+
        '<text x="'+pad+'" y="'+(h-10)+'" fill="#8f8d86" font-size="11">'+fmtUSD(range.min)+'</text>'+
        '<text x="'+(w/2-34)+'" y="'+(h-10)+'" fill="#8f8d86" font-size="11">'+fmtUSD(midX)+'</text>'+
        '<text x="'+(w-pad-70)+'" y="'+(h-10)+'" fill="#8f8d86" font-size="11">'+fmtUSD(range.max)+'</text>'+
        '<text x="6" y="'+(sy(maxY)+4).toFixed(1)+'" fill="#8f8d86" font-size="11">'+fmtUSD(maxY)+'</text>'+
        '<text x="6" y="'+(sy(minY)+4).toFixed(1)+'" fill="#8f8d86" font-size="11">'+fmtUSD(minY)+'</text>'+
        '</svg><div class="payoff-note">模拟基于当前执行腿价格，未单独加入手续费和资金费。</div>';
}

function payoffPriceRange(o) {
    var anchors = [];
    (o.legs || []).forEach(function(l) {
        var s = parseFloat(legStrike(o, l));
        var p = parseFloat(l.price);
        if (!isNaN(s) && s > 0) anchors.push(s);
        if (!isNaN(p) && p > 0) anchors.push(p);
    });
    var center = anchors.length ? anchors.reduce(function(a, b) { return a + b; }, 0) / anchors.length : 100;
    return {min: Math.max(0, center * 0.5), max: center * 1.5};
}

function strategyPayoffAtExpiry(o, expiryPrice) {
    return (o.legs || []).reduce(function(total, leg) {
        return total + legPayoffAtExpiry(o, leg, expiryPrice);
    }, 0);
}

function legPayoffAtExpiry(o, leg, expiryPrice) {
    var side = String(leg.side || '');
    var role = String(leg.role || '');
    var entry = parseFloat(leg.price);
    var size = parseFloat(leg.size || '1');
    var strike = parseFloat(legStrike(o, leg));
    if (isNaN(entry)) entry = 0;
    if (isNaN(size) || size <= 0) size = 1;
    var payoff;
    if (role.indexOf('call') >= 0) {
        payoff = Math.max(expiryPrice - strike, 0);
    } else if (role.indexOf('put') >= 0) {
        payoff = Math.max(strike - expiryPrice, 0);
    } else {
        payoff = expiryPrice;
    }
    var profit = side === 'buy' ? payoff - entry : entry - payoff;
    return profit * size;
}

function esc(v) {
    return String(v === null || v === undefined ? '' : v)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function domId(value) {
    return encodeURIComponent(String(value === null || value === undefined ? '' : value))
        .replace(/[!'()*]/g, function(ch) {
            return '%' + ch.charCodeAt(0).toString(16).toUpperCase();
        });
}

function fmtUSD(v) {
    if (v === null || v === undefined) return '—';
    var d = parseFloat(v);
    if (isNaN(d)) return v;
    if (Math.abs(d) >= 1000) return '$' + d.toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2});
    if (Math.abs(d) >= 1) return '$' + d.toFixed(2);
    if (Math.abs(d) >= 0.01) return '$' + d.toFixed(4);
    return '$' + d.toFixed(6);
}

function fmtAPY(v) {
    if (v === null || v === undefined) return '—';
    var d = parseFloat(v);
    if (isNaN(d)) return v;
    if (Math.abs(d) >= 0.01) return (d*100).toFixed(2) + '%';
    return (d*100).toFixed(4) + '%';
}

function tsToDate(ms) {
    if (!ms) return '—';
    return new Date(ms).toISOString().slice(0,10);
}

window.toggleDetail = toggleDetail;
window.simulatePayoff = simulatePayoff;

// auto-refresh countdown
var REFRESH_SECONDS = 6;
var _countdown = REFRESH_SECONDS;
function loadCachedScanData() {
    fetch('/api/scan?cache=1').then(function(r) { return r.json(); }).then(function(d) {
        if (d && d.opportunities) applyScanData(d);
    }).catch(function() {
        // Keep the current table visible if the cache refresh fails.
    });
}
function refreshCachedData() {
    fetch('/api/scan?live=1&exchanges=' + encodeURIComponent(selectedExchangeParam())).then(function(r) { return r.json(); }).then(function(d) {
        window.setTimeout(loadCachedScanData, 1000);
    }).catch(function() {
        // Keep the current table visible if the cache refresh fails.
        loadCachedScanData();
    });
}
setInterval(function() {
    if (refreshPaused) return;
    _countdown--;
    document.getElementById('refresh-timer').textContent = _countdown + 's';
    if (_countdown <= 0) {
        _countdown = REFRESH_SECONDS;
        refreshCachedData();
    }
}, 1000);

bindSortHeaders();
sortOppData(sortCol, sortAsc);
renderAll();
resumeScanIfNeeded();
