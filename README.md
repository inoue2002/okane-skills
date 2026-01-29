# okane-skills

[okane](https://okane-nine.vercel.app/)の家計簿データを分析する Claude Code スキル。

## 機能

| 機能 | コマンド | 説明 |
|------|----------|------|
| 残高予測 | `--forecast 6` | 6ヶ月後までの残高推移 |
| 出費チェック | `--check 500000 --date 2026-03-01` | その日にその金額使える？ |
| 危険検出 | `--danger --threshold 100000` | 残高が閾値を下回る日 |
| ログ圧縮 | `--compress --keep-months 3` | 古いデータを月次に圧縮 |
| 静的グラフ | `--chart --open` | PNG画像で出力 |
| インタラクティブ | `-i --open` | HTML（ホバーで詳細表示） |

## インストール

```bash
# Claude Code にスキルを追加
claude /install-skill /path/to/okane-skills
```

## 使用例

```bash
# 残高予測
python scripts/okane_analyzer.py data.json --forecast 6

# 2月に100万使えるかチェック
python scripts/okane_analyzer.py data.json --check 1000000 --date 2026-02-01

# インタラクティブグラフ（ブラウザで開く）
python scripts/okane_analyzer.py data.json -i --open
```

## スクリーンショット

### インタラクティブグラフ
ホバーで詳細表示、ドラッグでズーム、ダブルクリックでリセット

### 残高予測
```
| 月 | 残高 | 大きな出入り |
|----|------|-------------|
| 2026-01 | ¥1,500,000 | 給与(+¥300,000) |
| 2026-02 | ¥1,200,000 | 家賃(-¥100,000) |
```

## 依存関係

- Python 3.8+
- `python-dateutil`
- `matplotlib` (静的グラフ用、オプション)

## ライセンス

MIT
