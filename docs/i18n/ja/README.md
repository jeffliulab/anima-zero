# ANIMA Zero

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP-6f42c1.svg)](https://modelcontextprotocol.io)
[![MuJoCo](https://img.shields.io/badge/sim-MuJoCo-orange.svg)](https://mujoco.org)
[![Version](https://img.shields.io/github/v/tag/jeffliulab/anima-zero?label=version&color=lightgrey)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../../../LICENSE)

<a href="../../../README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/README.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="README.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="../fr/README.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="../es/README.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

> 🤖 **AI エージェントの方は、まず [AGENTS.md](../../../AGENTS.md) をお読みください** ——
> 機械向けの入口です：レイヤの規則、どの事実がどこにあるか、そして各コマンド。

## 概要

ANIMA Zero は具身ロボットのブレインです。考えるだけで、決して自分では動きません。
*何をするか*を決めるのがブレインで、*どう動くか*を決めるのが身体です。

「リビングに行って」と言ってみてください。地図も座標も部屋の一覧も持っておらず、
あるのはロボットの頭に付いたカメラだけです。そこから自分がどこにいるかを割り出し、
方向を選び、頼まれた部屋が見えるまで歩き続けます。ロボットは学習した歩容で歩くので、
脚は本当に地面を踏みます。瞬間移動はどこにもありません。

<div align="center">
<img src="../../images/nav-g1.gif" alt="ANIMA が人形ロボットを住宅の中で動かしている様子" width="820">
<br>
<img src="../../images/nav-go2.gif" alt="ANIMA が四足ロボットを住宅の中で動かしている様子" width="820">
<br>
<sub>ひとつのブレイン、ふたつの身体：上が G1 人形、下が Go2 四足。
どちらの映像も、左半分が ANIMA に届く唯一の入力で、右半分は実際に起きていること——
そして ANIMA はその右半分を見ることができません。</sub>
</div>

### なぜ「Zero」なのか

これはバージョン番号ではなくシリーズ名です。**Zero とは、この系統がオープンソースであり
続けるという意味**です。ブレインが ANIMA Zero、身体が SOMA Zero。将来もし商用版が出るとしても、
この系統を閉じるのではなく別の名前を名乗ります。プロジェクト全体が MIT です。

PyPI では `pip install anima-zero`、import は `import anima` です——`anima` という名前だけは
すでに別の人が登録していました。

## 主な特徴

- **ひとつのブレイン、異なる身体**：同じブレインのコードが Unitree Go2 四足と Unitree G1 人形を
  一行も変えずに動かします。違うのは目の高さだけで、0.38 m と 1.25 m です。
- **どんなワールドにもひとつのインターフェース**：ワールドは MCP 上で AWI を話す別プロセスです。
  ワールドを差し替えるとは URL を差し替えることであり、そのワールドは、あなたが中身を確認して
  承認するまで信頼されません。
- **一文から関節トルクまで**：ひとつの指示が脚の動きになるまでに 5 つの層を通り、
  それらの層は動作周波数にして 3 桁半ぶんの開きがあります。
- **いま何をしているかを覚えている**：2 つの状態レジスタがシステムプロンプトに同乗するので、
  60 手かかるターンでも目標を忘れず、すでに除外したものも忘れません。
- **監査でき、途中で止められる**：フレーム・思考・ツール呼び出しがすべて記録され、
  実行中のターンは飛行中に停止できます。

<div align="center">
<img src="../../images/eye-go2.png" alt="四足から見た視界" width="400">
<img src="../../images/eye-g1.png" alt="人形から見た視界" width="400">
<br>
<sub>同じリビングを、四足の目（左）と人形の目（右）から見たもの。
ロボットに何が見えるかが、何を結論できるかを決めます。だからこの場面は、
特定の機体に合わせて作るのではなく、現実に即して作ってあります。</sub>
</div>

## アーキテクチャ

ワールドはそれ自体がひとつのプログラムです。いまはシミュレーターで、いずれ実機になります。
ANIMA がその内側に手を突っ込むことはありません。ブレインが知ることはすべて 4 つのチャネルから
入り、することもすべて同じ 4 つを通って出ていきます。人間はブレインを完全に迂回して、
ワールド自身の画面から直接つつくこともできます。これが、両者が本当に分かれていることの
いちばん分かりやすい証拠です。

<div align="center">
<img src="../../images/arch-overview.svg" alt="人間・ANIMA・ワールド、その間にある AWI" width="860">
</div>

図の下側にある 3 つの端点——真値、映像、死活監視——は MCP を通らず、ブレインにも届きません。
この分離は意図的なものです。真値が知覚に入った瞬間、このワールドが試すはずだった能力は
ただで与えられてしまいます。

ひとつの指示の内側を見ると、層の分かれ方が具体的になります。ブレインは 1 ステップに 1 回考え、
歩容ポリシーは 50 Hz、物理は 500 Hz で回ります。その隔たりこそが、ここでいう System 2 と
System 1 の実体であり、ブレインが意図しか出せず関節角には決して触れない理由です。

<div align="center">
<img src="../../images/command-journey.svg" alt="一文から関節トルクまで" width="860">
</div>

ワールドは、都合よくではなく正直に報告します。学習した歩容は速度指令どおりには動きません——
旋回は流れ、歩行は届かない——だからワールドは実際に起きたことを測ってそのまま伝え、
ブレインは自分が要求した値ではなく、その報告のほうから自分の位置感覚を修正します。

```text
src/core/      オーケストレーター、AWI 契約、信頼ストア、安全ゲート
src/clients/   MCP クライアント層とワールド登録簿
src/session/   セッション、コンテキストウィンドウ、統一ログ
src/llm/       モデルアダプタ        src/presentation/  HTTP バックエンド
world/         各ワールド。それぞれが独立したプロセス
services/      ボードゲームエンジン  frontend/  ウェブアプリ   eval/  採点
```

## インストール

```bash
uv tool install anima-zero     # pipx install anima-zero でも、素の pip でも可
anima demo
```

これでワールドが起動し、ブレインが接続され、そのまま会話に入れます。API キーも node も、
ほかに入れるものもありません。ここで使われるブレインは考えません——ツールを 1 つ呼んで
結果を返すだけです——デモの目的は、あなたを感心させることではなく、そのループを見せることだからです。
キーを入れて `anima demo --brain gpt-5.4` とすれば、同じループを本当に考えるブレインで見られます。

```text
anima demo                    コマンド 1 つ、とにかく何かが起きる
anima chat --world W          ターミナルでの会話
anima run --say "..."         1 ターンだけ、スクリプト向け
anima serve                   ウェブアプリ用のバックエンド API
anima world add 名前 URL      ワールドを登録する——承認の前に中身を読むこと
anima doctor                  何が設定され、何に届くか
```

### ひととおり揃える

3 プロセス：ワールド、バックエンド、ウェブアプリ。場面とロボットは alice-house から来ており、
このリポジトリの隣を探します。別の場所にあるなら `HOUSENAV_ASSETS_ROOT` を設定してください。

```bash
cd world/sim-house-nav && pip install -e . && uvicorn server:app --port 8112
pip install -e . && cp .env.example .env      # API キーを入れるか、ローカルの Ollama を指す
anima serve
cd frontend && npm install && npm run dev
```

### ワールドを接続することは、信頼の決定である

ワールドはリモートのプロセスであり、そのワールド自身による自己紹介がブレインの
システムプロンプトに着地します。だから、あなたが中身を見て「はい」と言うまで、
ツールもガイダンスもブレインには届きません。`anima world add 名前 URL` は、
そのワールドが宣言している内容を表示してから尋ねます。承認は名前ではなく内容に紐づきます。
ワールドが別の姿で戻ってきたら、何が変わったかを添えてもう一度尋ねられます。
自分でワールドを開発している間は `ANIMA_TRUST_ALL=1` を設定してください。
これが何を守り、何を守らないかは [SECURITY.md](SECURITY.md) にあります。

## デモを動かす

ウェブアプリを開き、`sim-house-nav` に対してセッションを作り、「リビングに行って」と入力します。
中央の列にはロボットが見ているものと、あなたにだけ見える追跡カメラが別々に表示されます。
右の列には各ステップの全部——フレーム、推論、ツール呼び出し、ワールドの返答——が並びます。

<div align="center">
<img src="../../images/ui-chat-en.png" alt="ANIMA のウェブアプリ" width="880">
</div>

主張がもっともらしいだけなのか本当なのかを確かめたいときは、ワールドに直接聞いてください。
`curl -s localhost:8112/status` は、人が検証するための端点で、知覚には決して入りません。
差し替えはどれも一行です。身体は AWI ダッシュボードのドロップダウン（またはワールド起動前に
`HOUSENAV_ROBOT=g1`）、ブレインはウェブアプリのドロップダウン、ワールドはセッションを作るときに選びます。

リポジトリに同梱されているワールド：

| ワールド | ポート | 何であるか |
|---|---|---|
| [sim-house-nav](../../../world/sim-house-nav) | 8112 | 住宅ひとつと歩くロボット。四足でも人形でも |
| [sim-chess](../../../world/sim-chess) | 8102 | 唯一の真値を握り、指し返してくるチェスセット |
| [sim-desk](../../../world/sim-desk) | 8100 | 机とペンとキャンバス |
| [camera](../../../world/camera) | 8104 | 本物のウェブカメラ。ツールはゼロ——見えるが触れない |

### 実際のところ、どれくらいできるのか

目標の部屋 5 つを 1 回ずつ。最後のフレームは、モデルの主張と突き合わせてすべて手で確認しています：

| 目標 | ステップ | 結果 |
|---|---|---|
| キッチン | 9 | 正解——冷蔵庫、調理台、吊り戸棚がすべて画面内 |
| リビング | 5 | 正解——テレビ、ソファ、フロアランプ。議論の余地なし |
| 主寝室 | 34 | 不正解——大理石の床を「白いマットレス」と読んだ |
| 浴室 | 40 | 不正解——あれはキッチンだった |
| ランドリー | 60 | 未完——1 ターンあたりのステップ上限に当たった |

面白いのは否定的なほうの結果です。疑われていた原因は「0.38 m からだとキッチンと浴室が
似て見える」ことで、人形を足した理由のひとつもそれでした。ところが人形は 1.25 m から
コンロもレンジフードもはっきり見たうえで、やはり浴室だと言います。つまりこれは知覚の問題では
ありません。同じ戸口に向かって、モデルはいま探している部屋に合う筋書きを組み立てるのです。
次のリリースが狙うのは、知覚ではなく合否の判定基準のほうです。

うまくいった実行の記録は、フレームごとの検証つきで
[world/sim-house-nav/实测记录.md](../../../world/sim-house-nav/实测记录.md) にあります。

## 自分のワールドを足す

上の 4 チャネルを備えた標準の MCP サーバーを実装し、そのアドレスを `ANIMA_WORLDS` に足せば、
ブレインは変わらないままそれを動かします。最小の実装はメソッド 3 つ——`capabilities()`、
`observe()`、`invoke()`——で、どのワールドにも同梱されている `awi_mcp.py` アダプタで包みます。
いちばん単純な例は [sim-desk](../../../world/sim-desk)、いちばん完全な例は
[sim-house-nav](../../../world/sim-house-nav) を写してください。着手前にまず
[world/README.md](../../../world/README.md) を。契約は
[docs/awi-spec-v1.md](../../awi-spec-v1.md) に書かれており、`anima conformance <URL>` が
ワールドをそれに照らして検査します。

## 謝辞

場面、ロボットモデル、歩行ポリシーは [alice-house](https://github.com/jeffliulab/alice-house) から。
人形の旋回ポリシーは [unitree-g1-locomotion](https://github.com/jeffliulab/unitree-g1-locomotion) で
訓練しました。物理エンジンは [MuJoCo](https://mujoco.org)、ロボットモデルの出自は
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) です。
