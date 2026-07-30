# コントリビューション

<a href="../../../CONTRIBUTING.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/CONTRIBUTING.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="../fr/CONTRIBUTING.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="../es/CONTRIBUTING.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

> ANIMA Zero は**公開された研究用プロトタイプ**です。ポートフォリオ兼教材で、MIT ライセンス
> （[LICENSE](../../../LICENSE) を参照）。基本的にはメンテナーが一人で進めていますが、
> issue、フィードバック、小さな修正、ドキュメントの改善は歓迎します。まず
> [`README.md`](README.md) でアーキテクチャを、[行動規範](CODE_OF_CONDUCT.md) を読んでください。

## これは何か

ANIMA は具身ロボットの**ブレイン**です。System 2 であり、考えるだけで自分では動きません。
別プロセスとして動く**ワールド**（System 1）を、**AWI** というインターフェース越しに
観測し、操作します。AWI は MCP の上に載っています。フレームワークは領域非依存で、
特定のワールドについて何ひとつ決め打ちしていません。

## ローカルで動かす

```bash
uv tool install anima-zero && anima demo     # これだけ。キーも node も不要
```

開発時は 3 プロセス（ワールド・バックエンド・ウェブアプリ）です。README を参照してください。
設定（API キー、ローカル Ollama のアドレス、ワールド一覧）は
[`.env.example`](../../../.env.example) にあります。`world/sim-desk` は **git サブモジュール**
なので、`--recursive` を付けてクローンするか、あとから `git submodule update --init` を実行してください。

## 何かを足すとき

- **新しいワールド。** ワールドとは、3 つのプリミティブを話す標準の **MCP サーバー**
  （`/mcp` にマウント）です。**Tools**（何ができるか）、**Resources**（知覚、
  `anima://observation`）、**Prompts**（自分自身のガイダンス）。`anima world add 名前 URL`
  でアドレスを登録すれば、ブレインは一行も変わらずにそれを動かします。いちばん単純な例は
  [`world/sim-desk`](../../../world/sim-desk)、いちばん完全な例は
  [`world/sim-house-nav`](../../../world/sim-house-nav)。着手する前にまず
  [`world/README.md`](../../../world/README.md) を読んでください。
- **新しいブレイン（LLM）。** [`src/llm/README.md`](../../../src/llm/README.md) を参照。
  たいていのモデルは OpenAI 互換プロトコルを話すので、`src/llm/factory.py` の表に登録してください。
- **ツール。** ツールはワールドが MCP の `tools/list` で宣言します。名前、**いつ呼ぶべきで
  いつ呼ぶべきでないか**を述べた 3〜4 文、JSON Schema、そして `kind`。フレームワークは
  それらをネイティブの function call としてモデルに渡します。プロンプトに JSON を
  手書きすることは決してありません。

## この家のルール

その多くは、一度何かが壊れたから存在しています。`python scripts/selfcheck.py` が守っており、
CI が push のたびに実行します。

- **オーケストレーターはタスクに依存しないままでいる。** `src/core/orchestrator.py` は、
  自分がどのゲーム・どのタスクを動かしているかを知ってはいけません。タスク固有の知識は
  ワールドに属します。迷ったら——*このコードは別のワールドに対しても意味を持つか？*
- **「全集」は追記するもので、置き換えるものではない。** `ANIMA_WORLDS`、`.env.example`、
  既定の一覧、README の表——項目を足すことで既存の項目が消えてはいけません。これが
  厳格なルールなのは、実際に破ったことがあるからです。ワールドを 1 つ足したときに、
  別のワールドが UI から丸ごと消えました。
- **ハードコード禁止。** パスは導出するか環境から取ります。調整可能な数値は説明を添えて
  `src/config.py` に置き、インラインに書きません。モデルが判断すべきこと——意図、
  やめるかどうか、どの手を指すか——はモデルが判断します。キーワードの一覧に判断させてはいけません。
- **プレースホルダーは申告するもので、埋めるものではない。** どうしても残すなら、
  プルリクエストでそう言ってください。
- **あると言ったテストと能力は、本当になければならない。** 「ここはテストで守られている」と
  コメントに書いてあって実際にはない、というのは、データを捏造するのと同じ嘘です。

### 言語について

分け方は**読み手**によります。そしてこれは意図的なものです：

| 何を | 言語 |
|---|---|
| **モデル**が読むテキスト——システムプロンプト、ツールの説明、ワールドのガイダンス | **英語のみ。** 理由は `src/prompts.py` を参照 |
| **人**が読む UI 文言 | 英語・中国語・日本語をそろえて維持 |
| **人**が読むドキュメント——README、本ファイル、SECURITY、ROADMAP | 上の 3 言語に加えてフランス語・スペイン語。`docs/i18n/` 配下 |
| 公開 API の docstring——`core/awi.py`、各 `awi_mcp.py`、モジュール冒頭 | 英語と中国語 |
| なぜそうなっているかを説明する内部コメント | **中国語。そしてそれは意図的** |

最後の行は、抜けているのではなく実際の判断です。あれらのコメントはメンテナー自身の
思考であり、翻訳するとその有用さが平板になってしまいます。プロジェクトを使ううえでは
妨げになりませんし、*拡張する*ために必要な部分——契約、ガイダンス、ドキュメント——は
複数言語で用意されています。

### コミット

英語が先、中国語が後。履歴をざっと見たときに英語で読めるようにするためです：

```text
type: English summary line

English body — what changed and why.

---
中文说明：这次改了什么、为什么这么改。
```

差分ではなく理由を書いてください。*なぜ*を述べたコミットは、あとになって、*何を*を
言い直しただけのコミットよりずっと価値があります。リポジトリ直下の `.gitmessage` が
このテンプレートです。クローンごとに一度 `git config commit.template .gitmessage` を
実行すれば、自動で埋めてくれます。

## チェックリスト

- [ ] `pytest -q` が通る
- [ ] `ruff check .` が通る
- [ ] `python scripts/selfcheck.py` が通る
- [ ] README を触ったなら `python docs/check_readme.py` が通る
- [ ] 挙動が変わったなら **すべての** CHANGELOG（英語版はリポジトリ直下、中日は `docs/i18n/` 配下）と、
      該当する README を更新した
- [ ] **足したガードが本当に発火する。** わざと壊してテストが赤くなるのを見て、戻す。
      失敗するところを誰も見ていないガードは、機能しているかを誰も知らないガードです。
      このプロジェクトでは、黙って守るのをやめていたガードを 4 つ捕まえています。

## 実機について

⚠️ 実機に触れるコードとコマンドには物理的な危険があります。**実行する人は機械のそばに
いなければなりません。** [SECURITY.md](SECURITY.md) を参照してください。

## 報告

issue を立ててください。セキュリティに関することは、まず [SECURITY.md](SECURITY.md) を、
特に「ワールドを接続することは信頼の決定である」という第 2 節を読んでください。

ライセンス：本プロジェクトは [MIT](../../../LICENSE) で公開されています。コントリビュートは、
あなたの貢献も同じく MIT で提供することへの同意を意味します。MIT はすでにクローズドソースでの
商用利用を許しているため、署名すべき CLA も、デュアルライセンスの取り決めもありません。
どのリリースにどの条項が適用されるかは [NOTICE](../../../NOTICE) に記録されています。
