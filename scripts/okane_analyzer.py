#!/usr/bin/env python3
"""
okane-backup JSONファイルの分析・予測スクリプト
"""

import json
import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from dateutil.relativedelta import relativedelta

# グラフ用（オプション）
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib import rcParams
    # 日本語フォント設定
    rcParams['font.family'] = 'sans-serif'
    rcParams['font.sans-serif'] = ['Hiragino Sans', 'Hiragino Kaku Gothic ProN', 'Yu Gothic', 'Meiryo', 'sans-serif']
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def load_json(file_path: str) -> dict:
    """JSONファイルを読み込む"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(file_path: str, data: dict):
    """JSONファイルを保存"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_currency(amount: int) -> str:
    """金額をフォーマット"""
    if amount >= 0:
        return f"¥{amount:,}"
    return f"-¥{abs(amount):,}"


def get_balance_at_date(data: dict, target_date: str) -> int:
    """指定日時点の残高を計算"""
    balance = data.get('initialBalance', 0)
    for t in data['transactions']:
        if t['date'] <= target_date:
            if t['type'] == 'income':
                balance += t['amount']
            else:
                balance -= t['amount']
    return balance


def compress_logs(data: dict, keep_months: int = 3) -> dict:
    """古いログを月次サマリーに圧縮

    keep_months: 直近何ヶ月分は詳細を保持するか
    """
    today = datetime.now()
    cutoff = (today - relativedelta(months=keep_months)).strftime('%Y-%m')

    old_transactions = []
    new_transactions = []
    monthly_summary = defaultdict(lambda: {'income': 0, 'expense': 0})

    for t in data['transactions']:
        month = t['date'][:7]
        if month < cutoff:
            if t['type'] == 'income':
                monthly_summary[month]['income'] += t['amount']
            else:
                monthly_summary[month]['expense'] += t['amount']
        else:
            new_transactions.append(t)

    # 月次サマリーを圧縮トランザクションに変換
    compressed = []
    for month in sorted(monthly_summary.keys()):
        s = monthly_summary[month]
        if s['income'] > 0:
            compressed.append({
                'id': f'compressed-{month}-income',
                'date': f'{month}-01',
                'type': 'income',
                'amount': s['income'],
                'description': f'{month}収入合計（圧縮）'
            })
        if s['expense'] > 0:
            compressed.append({
                'id': f'compressed-{month}-expense',
                'date': f'{month}-01',
                'type': 'expense',
                'amount': s['expense'],
                'description': f'{month}支出合計（圧縮）'
            })

    new_data = data.copy()
    new_data['transactions'] = compressed + new_transactions
    new_data['compressed'] = True
    new_data['compressedAt'] = datetime.now().isoformat()

    return new_data


def forecast_balance(data: dict, months_ahead: int = 6) -> list:
    """将来の残高を予測

    既存の将来取引を考慮して残高推移を表示
    """
    today = datetime.now()
    results = []

    for i in range(months_ahead + 1):
        target = today + relativedelta(months=i)
        # 月末時点で計算
        if i == 0:
            target_date = today.strftime('%Y-%m-%d')
        else:
            # 月末を計算
            next_month = target.replace(day=28) + timedelta(days=4)
            target_date = (next_month - timedelta(days=next_month.day)).strftime('%Y-%m-%d')

        balance = get_balance_at_date(data, target_date)

        # その月の大きな出入りを抽出
        month_str = target.strftime('%Y-%m')
        big_items = []
        for t in data['transactions']:
            if t['date'].startswith(month_str) and t['amount'] >= 100000:
                big_items.append(t)

        results.append({
            'month': month_str,
            'date': target_date,
            'balance': balance,
            'big_items': big_items
        })

    return results


def check_affordability(data: dict, amount: int, target_date: str) -> dict:
    """指定日に指定金額の出費が可能かチェック"""
    # 出費前の残高
    balance_before = get_balance_at_date(data, target_date)
    balance_after = balance_before - amount

    # その日以降の予定支出を取得
    upcoming_expenses = []
    for t in data['transactions']:
        if t['date'] > target_date and t['type'] == 'expense':
            upcoming_expenses.append(t)

    # 次の大きな支出までの余裕
    total_upcoming = sum(t['amount'] for t in upcoming_expenses[:5])  # 次の5件

    return {
        'target_date': target_date,
        'expense_amount': amount,
        'balance_before': balance_before,
        'balance_after': balance_after,
        'can_afford': balance_after >= 0,
        'safety_margin': balance_after,
        'upcoming_expenses': upcoming_expenses[:5],
        'warning': balance_after < 100000  # 10万円以下は警告
    }


def find_danger_points(data: dict, threshold: int = 0) -> list:
    """残高が危険水準を下回るポイントを検出"""
    # 全取引を日付順にソート
    transactions = sorted(data['transactions'], key=lambda x: x['date'])

    balance = data.get('initialBalance', 0)
    danger_points = []
    balance_history = []

    current_date = None
    daily_balance = balance

    for t in transactions:
        if current_date and t['date'] != current_date:
            balance_history.append({'date': current_date, 'balance': daily_balance})
            if daily_balance <= threshold:
                danger_points.append({
                    'date': current_date,
                    'balance': daily_balance,
                    'shortfall': threshold - daily_balance
                })

        if t['type'] == 'income':
            balance += t['amount']
        else:
            balance -= t['amount']

        daily_balance = balance
        current_date = t['date']

    # 最後の日
    if current_date:
        balance_history.append({'date': current_date, 'balance': daily_balance})
        if daily_balance <= threshold:
            danger_points.append({
                'date': current_date,
                'balance': daily_balance,
                'shortfall': threshold - daily_balance
            })

    return danger_points


def print_forecast(results: list):
    """残高予測を表示"""
    print("\n## 残高予測\n")
    print("| 月 | 残高 | 大きな出入り |")
    print("|----|------|-------------|")

    for r in results:
        big_items_str = ""
        if r['big_items']:
            items = [f"{t['description']}({'+' if t['type']=='income' else '-'}{format_currency(t['amount'])})"
                    for t in r['big_items']]
            big_items_str = ", ".join(items)

        balance_str = format_currency(r['balance'])
        if r['balance'] < 0:
            balance_str = f"**{balance_str}** ⚠️"
        elif r['balance'] < 100000:
            balance_str = f"{balance_str} ⚠️"

        print(f"| {r['month']} | {balance_str} | {big_items_str} |")


def print_affordability(result: dict):
    """出費可能性チェック結果を表示"""
    print(f"\n## {result['target_date']}に{format_currency(result['expense_amount'])}の出費チェック\n")

    status = "✅ 可能" if result['can_afford'] else "❌ 不足"
    if result['warning'] and result['can_afford']:
        status = "⚠️ ギリギリ"

    print(f"**判定: {status}**\n")
    print("| 項目 | 金額 |")
    print("|------|------|")
    print(f"| 出費前残高 | {format_currency(result['balance_before'])} |")
    print(f"| 出費額 | {format_currency(result['expense_amount'])} |")
    print(f"| 出費後残高 | {format_currency(result['balance_after'])} |")

    if result['upcoming_expenses']:
        print("\n### その後の予定支出\n")
        print("| 日付 | 内容 | 金額 |")
        print("|------|------|------|")
        for t in result['upcoming_expenses']:
            print(f"| {t['date']} | {t['description']} | {format_currency(t['amount'])} |")


def print_danger_points(points: list):
    """危険ポイントを表示"""
    print("\n## ⚠️ 残高不足の警告\n")

    if not points:
        print("危険なポイントはありません ✅")
        return

    print("| 日付 | 残高 | 不足額 |")
    print("|------|------|--------|")
    for p in points:
        print(f"| {p['date']} | {format_currency(p['balance'])} | {format_currency(p['shortfall'])} |")


def generate_balance_chart(data: dict, months_ahead: int = 6, output_path: str = None, open_file: bool = False) -> str:
    """残高推移グラフを生成"""
    if not HAS_MATPLOTLIB:
        print("❌ matplotlib がインストールされていません")
        return None

    # 全取引を日付順にソート
    transactions = sorted(data['transactions'], key=lambda x: x['date'])

    if not transactions:
        print("❌ 取引データがありません")
        return None

    # 日付ごとの残高を計算
    balance = data.get('initialBalance', 0)
    dates = []
    balances = []

    # 開始日から終了日までの残高推移
    start_date = datetime.strptime(transactions[0]['date'], '%Y-%m-%d')
    end_date = datetime.now() + relativedelta(months=months_ahead)

    # 日ごとの残高を計算
    current_date = start_date
    tx_index = 0

    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')

        # その日の取引を処理
        while tx_index < len(transactions) and transactions[tx_index]['date'] <= date_str:
            t = transactions[tx_index]
            if t['type'] == 'income':
                balance += t['amount']
            else:
                balance -= t['amount']
            tx_index += 1

        dates.append(current_date)
        balances.append(balance)
        current_date += timedelta(days=1)

    # グラフ作成
    fig, ax = plt.subplots(figsize=(12, 6))

    # 残高ライン
    ax.plot(dates, balances, 'b-', linewidth=2, label='残高')

    # 今日の縦線
    today = datetime.now()
    ax.axvline(x=today, color='g', linestyle='--', alpha=0.5, label='今日')

    # 大きな出入りにマーカー
    for t in data['transactions']:
        if t['amount'] >= 200000:  # 20万円以上
            t_date = datetime.strptime(t['date'], '%Y-%m-%d')
            if start_date <= t_date <= end_date:
                balance_at_date = get_balance_at_date(data, t['date'])
                color = 'green' if t['type'] == 'income' else 'red'
                marker = '^' if t['type'] == 'income' else 'v'
                ax.scatter([t_date], [balance_at_date], color=color, s=100, marker=marker, zorder=5)
                # ラベル
                ax.annotate(f"{t['description']}\n{format_currency(t['amount'])}",
                           (t_date, balance_at_date),
                           textcoords="offset points",
                           xytext=(0, 15 if t['type'] == 'income' else -25),
                           ha='center', fontsize=8,
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))

    # 軸設定
    ax.set_xlabel('日付')
    ax.set_ylabel('残高（円）')
    ax.set_title('残高推移予測')

    # Y軸を円表記に
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'¥{int(x):,}'))

    # X軸を月表記に
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.xticks(rotation=45)

    # グリッド
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left')

    plt.tight_layout()

    # 保存
    if not output_path:
        output_path = f"okane-chart-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"

    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"✅ グラフを保存しました: {output_path}")

    # ファイルを開く
    if open_file:
        open_file_in_os(output_path)

    return output_path


def open_file_in_os(file_path: str):
    """OSに応じてファイルを開く"""
    if sys.platform == 'darwin':  # macOS
        subprocess.run(['open', file_path])
    elif sys.platform == 'win32':  # Windows
        subprocess.run(['start', file_path], shell=True)
    else:  # Linux
        subprocess.run(['xdg-open', file_path])


def generate_interactive_chart(data: dict, months_ahead: int = 6, output_path: str = None, open_file: bool = False) -> str:
    """インタラクティブなHTML残高推移グラフを生成"""

    # 全取引を日付順にソート
    transactions = sorted(data['transactions'], key=lambda x: x['date'])

    if not transactions:
        print("❌ 取引データがありません")
        return None

    # 日付ごとの残高を計算
    balance = data.get('initialBalance', 0)
    start_date = datetime.strptime(transactions[0]['date'], '%Y-%m-%d')
    end_date = datetime.now() + relativedelta(months=months_ahead)

    # 日ごとの残高を計算
    dates = []
    balances = []
    current_date = start_date
    tx_index = 0

    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')

        while tx_index < len(transactions) and transactions[tx_index]['date'] <= date_str:
            t = transactions[tx_index]
            if t['type'] == 'income':
                balance += t['amount']
            else:
                balance -= t['amount']
            tx_index += 1

        dates.append(date_str)
        balances.append(balance)
        current_date += timedelta(days=1)

    # 大きな取引のマーカーデータ
    big_transactions = []
    for t in data['transactions']:
        if t['amount'] >= 200000:
            t_date = t['date']
            if start_date.strftime('%Y-%m-%d') <= t_date <= end_date.strftime('%Y-%m-%d'):
                balance_at = get_balance_at_date(data, t_date)
                big_transactions.append({
                    'date': t_date,
                    'balance': balance_at,
                    'description': t['description'],
                    'amount': t['amount'],
                    'type': t['type']
                })

    # 今日の日付
    today = datetime.now().strftime('%Y-%m-%d')

    # HTML生成
    html_content = f'''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>残高推移予測</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            text-align: center;
            color: #333;
        }}
        #chart {{
            width: 100%;
            height: 600px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .info {{
            text-align: center;
            color: #666;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <h1>残高推移予測</h1>
    <div id="chart"></div>
    <p class="info">グラフ上をホバーで詳細表示 / ドラッグでズーム / ダブルクリックでリセット</p>

    <script>
        const dates = {json.dumps(dates)};
        const balances = {json.dumps(balances)};
        const bigTransactions = {json.dumps(big_transactions, ensure_ascii=False)};
        const today = "{today}";

        // メインの残高ライン
        const balanceLine = {{
            x: dates,
            y: balances,
            type: 'scatter',
            mode: 'lines',
            name: '残高',
            line: {{ color: '#2196F3', width: 2 }},
            hovertemplate: '%{{x}}<br>残高: ¥%{{y:,.0f}}<extra></extra>'
        }};

        // 収入マーカー
        const incomeMarkers = {{
            x: bigTransactions.filter(t => t.type === 'income').map(t => t.date),
            y: bigTransactions.filter(t => t.type === 'income').map(t => t.balance),
            type: 'scatter',
            mode: 'markers',
            name: '収入（20万以上）',
            marker: {{ color: '#4CAF50', size: 12, symbol: 'triangle-up' }},
            text: bigTransactions.filter(t => t.type === 'income').map(t => t.description + '<br>+¥' + t.amount.toLocaleString()),
            hovertemplate: '%{{x}}<br>%{{text}}<br>残高: ¥%{{y:,.0f}}<extra></extra>'
        }};

        // 支出マーカー
        const expenseMarkers = {{
            x: bigTransactions.filter(t => t.type === 'expense').map(t => t.date),
            y: bigTransactions.filter(t => t.type === 'expense').map(t => t.balance),
            type: 'scatter',
            mode: 'markers',
            name: '支出（20万以上）',
            marker: {{ color: '#f44336', size: 12, symbol: 'triangle-down' }},
            text: bigTransactions.filter(t => t.type === 'expense').map(t => t.description + '<br>-¥' + t.amount.toLocaleString()),
            hovertemplate: '%{{x}}<br>%{{text}}<br>残高: ¥%{{y:,.0f}}<extra></extra>'
        }};

        const layout = {{
            xaxis: {{
                title: '日付',
                showgrid: true,
                gridcolor: '#eee'
            }},
            yaxis: {{
                title: '残高（円）',
                showgrid: true,
                gridcolor: '#eee',
                tickformat: ',.0f',
                tickprefix: '¥'
            }},
            shapes: [{{
                type: 'line',
                x0: today,
                x1: today,
                y0: 0,
                y1: 1,
                yref: 'paper',
                line: {{ color: '#4CAF50', width: 2, dash: 'dash' }}
            }}],
            annotations: [{{
                x: today,
                y: 1,
                yref: 'paper',
                text: '今日',
                showarrow: false,
                yanchor: 'bottom',
                font: {{ color: '#4CAF50' }}
            }}],
            hovermode: 'x unified',
            legend: {{
                orientation: 'h',
                y: -0.15
            }},
            margin: {{ t: 30, b: 80 }}
        }};

        const config = {{
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            displaylogo: false
        }};

        Plotly.newPlot('chart', [balanceLine, incomeMarkers, expenseMarkers], layout, config);
    </script>
</body>
</html>'''

    # 保存
    if not output_path:
        output_path = f"okane-chart-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ インタラクティブグラフを保存しました: {output_path}")

    if open_file:
        open_file_in_os(output_path)

    return output_path


def main():
    parser = argparse.ArgumentParser(description='okane残高予測・分析')
    parser.add_argument('file', help='JSONファイルパス')

    # 予測・分析コマンド
    parser.add_argument('--forecast', type=int, metavar='MONTHS',
                       help='N ヶ月後までの残高予測')
    parser.add_argument('--check', type=int, metavar='AMOUNT',
                       help='指定金額の出費が可能かチェック')
    parser.add_argument('--date', help='基準日（YYYY-MM-DD）')
    parser.add_argument('--danger', action='store_true',
                       help='残高が危険水準になるポイントを検出')
    parser.add_argument('--threshold', type=int, default=0,
                       help='危険判定の閾値（デフォルト: 0円）')

    # ログ圧縮
    parser.add_argument('--compress', action='store_true',
                       help='古いログを圧縮')
    parser.add_argument('--keep-months', type=int, default=3,
                       help='直近何ヶ月分を保持するか（デフォルト: 3）')
    parser.add_argument('--output', '-o', help='出力ファイルパス')

    # グラフ生成
    parser.add_argument('--chart', action='store_true',
                       help='残高推移グラフを生成（PNG）')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='インタラクティブグラフを生成（HTML）')
    parser.add_argument('--chart-months', type=int, default=6,
                       help='グラフに表示する将来の月数（デフォルト: 6）')
    parser.add_argument('--open', action='store_true',
                       help='生成したグラフを自動で開く')

    args = parser.parse_args()
    data = load_json(args.file)

    # ログ圧縮
    if args.compress:
        compressed = compress_logs(data, args.keep_months)
        output_path = args.output or args.file.replace('.json', '-compressed.json')
        save_json(output_path, compressed)

        original_count = len(data['transactions'])
        new_count = len(compressed['transactions'])
        print(f"✅ ログを圧縮しました")
        print(f"   {original_count}件 → {new_count}件")
        print(f"   保存先: {output_path}")
        return

    # 残高予測
    if args.forecast:
        results = forecast_balance(data, args.forecast)
        print_forecast(results)
        return

    # 出費可能性チェック
    if args.check:
        target_date = args.date or datetime.now().strftime('%Y-%m-%d')
        result = check_affordability(data, args.check, target_date)
        print_affordability(result)
        return

    # 危険ポイント検出
    if args.danger:
        points = find_danger_points(data, args.threshold)
        print_danger_points(points)
        return

    # グラフ生成
    if args.chart:
        output_path = args.output or None
        generate_balance_chart(data, args.chart_months, output_path, args.open)
        return

    # インタラクティブグラフ生成
    if args.interactive:
        output_path = args.output or None
        generate_interactive_chart(data, args.chart_months, output_path, args.open)
        return

    # デフォルト: 6ヶ月予測 + 危険ポイント
    results = forecast_balance(data, 6)
    print_forecast(results)

    points = find_danger_points(data, 0)
    print_danger_points(points)


if __name__ == '__main__':
    main()
