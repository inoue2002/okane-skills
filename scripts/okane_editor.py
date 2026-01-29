#!/usr/bin/env python3
"""
okane-backup JSONファイルの編集スクリプト
取引の追加・編集・削除を行う
"""

import json
import argparse
from datetime import datetime
import random
import string


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


def generate_id() -> str:
    """ユニークIDを生成"""
    timestamp = int(datetime.now().timestamp() * 1000)
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
    return f"{timestamp}-{random_str}"


def add_transaction(data: dict, date: str, tx_type: str, amount: int, description: str) -> dict:
    """取引を追加"""
    new_tx = {
        'id': generate_id(),
        'date': date,
        'type': tx_type,
        'amount': amount,
        'description': description
    }
    data['transactions'].append(new_tx)
    data['transactions'] = sorted(data['transactions'], key=lambda x: x['date'])
    return new_tx


def edit_transaction(data: dict, tx_id: str, date: str = None, tx_type: str = None,
                     amount: int = None, description: str = None) -> dict:
    """取引を編集"""
    for tx in data['transactions']:
        if tx['id'] == tx_id:
            if date:
                tx['date'] = date
            if tx_type:
                tx['type'] = tx_type
            if amount is not None:
                tx['amount'] = amount
            if description:
                tx['description'] = description
            data['transactions'] = sorted(data['transactions'], key=lambda x: x['date'])
            return tx
    return None


def delete_transaction(data: dict, tx_id: str) -> dict:
    """取引を削除"""
    for i, tx in enumerate(data['transactions']):
        if tx['id'] == tx_id:
            deleted = data['transactions'].pop(i)
            return deleted
    return None


def search_transactions(data: dict, keyword: str = None, tx_type: str = None,
                        start_date: str = None, end_date: str = None,
                        min_amount: int = None, max_amount: int = None) -> list:
    """取引を検索"""
    transactions = data['transactions']

    if tx_type:
        transactions = [t for t in transactions if t['type'] == tx_type]
    if start_date:
        transactions = [t for t in transactions if t['date'] >= start_date]
    if end_date:
        transactions = [t for t in transactions if t['date'] <= end_date]
    if min_amount is not None:
        transactions = [t for t in transactions if t['amount'] >= min_amount]
    if max_amount is not None:
        transactions = [t for t in transactions if t['amount'] <= max_amount]
    if keyword:
        transactions = [t for t in transactions if keyword.lower() in t['description'].lower()]

    return sorted(transactions, key=lambda x: x['date'], reverse=True)


def print_transactions(transactions: list, show_full_id: bool = False):
    """取引一覧を表示"""
    if not transactions:
        print("取引が見つかりません")
        return

    print(f"\n## 取引一覧（{len(transactions)}件）\n")
    print("| ID | 日付 | 種別 | 金額 | 説明 |")
    print("|----|------|------|------|------|")
    for t in transactions:
        type_str = "収入" if t['type'] == 'income' else "支出"
        id_str = t['id'] if show_full_id else f"{t['id'][:15]}..."
        print(f"| `{id_str}` | {t['date']} | {type_str} | {format_currency(t['amount'])} | {t['description']} |")


def print_summary(data: dict):
    """データサマリーを表示"""
    transactions = data['transactions']
    income_total = sum(t['amount'] for t in transactions if t['type'] == 'income')
    expense_total = sum(t['amount'] for t in transactions if t['type'] == 'expense')

    print(f"\n## サマリー\n")
    print(f"- 取引件数: {len(transactions)}件")
    print(f"- 収入合計: {format_currency(income_total)}")
    print(f"- 支出合計: {format_currency(expense_total)}")
    print(f"- 残高: {format_currency(income_total - expense_total)}")


def main():
    parser = argparse.ArgumentParser(description='okane JSON編集ツール')
    parser.add_argument('file', help='JSONファイルパス')

    # 操作モード
    parser.add_argument('--list', '-l', action='store_true',
                       help='取引一覧を表示')
    parser.add_argument('--add', '-a', action='store_true',
                       help='取引を追加')
    parser.add_argument('--edit', '-e', metavar='ID',
                       help='取引を編集（IDを指定）')
    parser.add_argument('--delete', '-d', metavar='ID',
                       help='取引を削除（IDを指定）')
    parser.add_argument('--search', '-s', metavar='KEYWORD',
                       help='取引を検索')

    # 取引データ
    parser.add_argument('--date', help='日付（YYYY-MM-DD）')
    parser.add_argument('--type', '-t', choices=['income', 'expense'],
                       help='種別（income/expense）')
    parser.add_argument('--amount', type=int, help='金額')
    parser.add_argument('--desc', help='説明')

    # フィルター
    parser.add_argument('--from', dest='start_date', help='開始日（YYYY-MM-DD）')
    parser.add_argument('--to', dest='end_date', help='終了日（YYYY-MM-DD）')
    parser.add_argument('--min', type=int, dest='min_amount', help='最小金額')
    parser.add_argument('--max', type=int, dest='max_amount', help='最大金額')
    parser.add_argument('--limit', type=int, default=50, help='表示件数（デフォルト: 50）')

    # 出力
    parser.add_argument('--output', '-o', help='出力ファイルパス')
    parser.add_argument('--full-id', action='store_true', help='IDを省略せず表示')

    args = parser.parse_args()
    data = load_json(args.file)

    # 一覧表示
    if args.list:
        transactions = search_transactions(
            data,
            tx_type=args.type,
            start_date=args.start_date,
            end_date=args.end_date,
            min_amount=args.min_amount,
            max_amount=args.max_amount
        )[:args.limit]
        print_transactions(transactions, args.full_id)
        print_summary(data)
        return

    # 検索
    if args.search:
        transactions = search_transactions(
            data,
            keyword=args.search,
            tx_type=args.type,
            start_date=args.start_date,
            end_date=args.end_date,
            min_amount=args.min_amount,
            max_amount=args.max_amount
        )[:args.limit]
        print_transactions(transactions, args.full_id)
        return

    # 追加
    if args.add:
        if not all([args.date, args.type, args.amount, args.desc]):
            print("❌ --add には --date, --type, --amount, --desc が必要です")
            print("\n例:")
            print("  収入: --add --date 2026-02-01 --type income --amount 300000 --desc 給与")
            print("  支出: --add --date 2026-02-01 --type expense --amount 80000 --desc 家賃")
            return

        new_tx = add_transaction(data, args.date, args.type, args.amount, args.desc)
        output_path = args.output or args.file
        save_json(output_path, data)

        print(f"✅ 取引を追加しました")
        print(f"   ID: {new_tx['id']}")
        print(f"   日付: {new_tx['date']}")
        print(f"   種別: {'収入' if new_tx['type'] == 'income' else '支出'}")
        print(f"   金額: {format_currency(new_tx['amount'])}")
        print(f"   説明: {new_tx['description']}")
        print(f"   保存先: {output_path}")
        return

    # 編集
    if args.edit:
        if not any([args.date, args.type, args.amount, args.desc]):
            print("❌ --edit には編集内容（--date, --type, --amount, --desc のいずれか）が必要です")
            return

        edited = edit_transaction(data, args.edit, args.date, args.type, args.amount, args.desc)
        if edited:
            output_path = args.output or args.file
            save_json(output_path, data)
            print(f"✅ 取引を編集しました")
            print(f"   ID: {edited['id']}")
            print(f"   日付: {edited['date']}")
            print(f"   種別: {'収入' if edited['type'] == 'income' else '支出'}")
            print(f"   金額: {format_currency(edited['amount'])}")
            print(f"   説明: {edited['description']}")
            print(f"   保存先: {output_path}")
        else:
            print(f"❌ ID '{args.edit}' の取引が見つかりません")
            print("💡 --list --full-id でIDを確認してください")
        return

    # 削除
    if args.delete:
        deleted = delete_transaction(data, args.delete)
        if deleted:
            output_path = args.output or args.file
            save_json(output_path, data)
            print(f"✅ 取引を削除しました")
            print(f"   日付: {deleted['date']}")
            print(f"   種別: {'収入' if deleted['type'] == 'income' else '支出'}")
            print(f"   金額: {format_currency(deleted['amount'])}")
            print(f"   説明: {deleted['description']}")
            print(f"   保存先: {output_path}")
        else:
            print(f"❌ ID '{args.delete}' の取引が見つかりません")
            print("💡 --list --full-id でIDを確認してください")
        return

    # デフォルト: 一覧表示
    transactions = search_transactions(data)[:args.limit]
    print_transactions(transactions, args.full_id)
    print_summary(data)


if __name__ == '__main__':
    main()
