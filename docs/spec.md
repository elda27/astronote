以下、astronote の仕様書案です。
初期実装は 静的解析オンリー を前提にしています。


---

astronote 仕様書

1. 概要

1.1 ツール名

astronote

1.2 名称の意図

astronote は AST to Reprodceble Output NOTEbook の略称である。
Python スクリプトを AST ベースで解析し、再現可能で静的に構成された Jupyter Notebook を生成することを目的とする。
あわせて、宇宙飛行士を意味する astronaut に近い響きを持たせ、Notebook を生成・展開するツールであることを表現する。

1.3 目的

astronote は、スクリプトベースで開発された Python コードから、提出・共有・再実験に適した Jupyter Notebook を生成するためのツールである。
特に、Kaggle のような Notebook 実行前提の環境に対し、コードベースの肥大化や Notebook 中心開発への回帰を避けつつ、script-first な開発体験を維持することを目的とする。

1.4 非目的

astronote は以下を初期実装の対象外とする。

実行時のモンキーパッチや動的コード書き換えの完全追跡

任意の Python コードの完全な意味解析

ユーザーが編集した Notebook を正本として扱う運用

リッチな双方向 Notebook 編集機能

実行結果や出力セルの内容を正本として管理すること



---

2. 基本方針

2.1 Script-first

astronote は、Python スクリプトまたはモジュールを正本とする。
生成される Notebook は派生成果物であり、読み取り・提出・共有・再実行のために用いる。

2.2 AST-first

解析は Python AST を中心に行う。
コメントや人手の編集慣習に依存せず、構文的に安定した変換を行う。

2.3 Read Only Notebook

生成された Notebook は、原則として Read Only 的な成果物 とみなす。
必要に応じて一部セルの差分更新や保持は行うが、正本は常にスクリプト側にある。

2.4 Static-first

初期実装では 静的解析のみ を対象とする。
実行時に関数呼び出しを捕捉する仕組みは将来拡張として予約し、現時点では変換器の本体に含めない。

2.5 Reproducibility-first

Notebook 生成時に使用したハイパーパラメータ、推定値、入力ソース、変換メタ情報を保持し、再生成可能性を担保する。


---

3. 想定ユースケース

3.1 Kaggle 提出用 Notebook の生成

ユーザーはローカルで src/ レイアウトの Python プロジェクトとして開発し、astronote により提出用 Notebook を生成する。

3.2 Script から共有用 Notebook を生成

調査・分析・推論コードを Notebook 形式で共有したいが、Notebook を主編集面にしたくない場合に利用する。

3.3 Papermill 再実験向け Notebook の生成

ハイパーパラメータセルを持つ Notebook を生成し、Papermill により複数条件で再実行する。

3.4 実験条件の Git 管理

ハイパーパラメータを JSON ファイルで保存し、Notebook 生成条件を Git 管理する。


---

4. 用語定義

4.1 Source Script

astronote が解析対象とする Python スクリプトまたはモジュール。

4.2 Entrypoint

Notebook 生成対象となる実行起点の関数。
デコレータにより明示的に指定する。

4.3 Parameter File

Notebook 生成時に使用するハイパーパラメータを記述した JSON ファイル。

4.4 Static IR

AST 解析により得られる中間表現。
Entrypoint、シグネチャ、型ヒント、callsite 推定値、import 展開計画などを保持する。

4.5 Resolved IR

Static IR に対してパラメータ解決を行った後の中間表現。
最終的な Notebook 生成入力となる。

4.6 Generated Cell

astronote により自動生成された Notebook セル。

4.7 User-preserved Cell

ユーザー編集を保持対象とする Notebook セル。
初期実装では限定的に扱う。


---

5. 入力

5.1 必須入力

Python スクリプトまたはモジュールパス


5.2 任意入力

Parameter File（JSON）

CLI での parameter override

pyproject.toml のツール設定

環境変数

既存 Notebook（update 時）



---

6. 出力

6.1 主出力

Jupyter Notebook (.ipynb)


6.2 補助出力

Parameter schema 出力

Resolved manifest 出力

静的解析結果表示

差分更新結果



---

7. Entrypoint 指定仕様

7.1 指定方式

Entrypoint はデコレータにより明示する。

例:

from astronote import notebook_entry

@notebook_entry
def run(config: TrainConfig) -> None:
    ...

7.2 許容形式

初期実装では以下を対象とする。

@notebook_entry

@notebook_entry(...)

import alias を伴う単純な別名利用


7.3 非対応

初期実装では以下を保証しない。

実行時にのみ確定する decorator 実体

複雑な re-export を経由した decorator 解決

動的 import を伴う decorator 定義


7.4 複数 entrypoint

1ファイル中に複数の entrypoint が存在してよい。
CLI 側で明示選択できるものとする。
未指定時は以下の優先順位で解決する。

1. entrypoint が1つのみなら自動選択


2. 複数ある場合はエラー


3. 明示指定があればそれを優先




---

8. パラメータ推定仕様

8.1 基本方針

Entrypoint のシグネチャと型ヒントを解析し、Notebook の parameter cell を生成する。

8.2 引数解釈ルール

8.2.1 引数が0個

parameter cell を省略可能とする。

8.2.2 引数が1個

以下の順に structured parameter として扱うか判定する。

1. dataclass として解釈可能


2. 明示対応 extractor により structured object として解釈可能


3. それ以外は単一パラメータとして扱う



8.2.3 引数が2個以上

各引数を個別パラメータとして扱う。


---

8.3 Structured parameter 対応

初期実装では以下を優先対応対象とする。

dataclasses.dataclass

将来的に extractor plugin による拡張を許可


8.3.1 dataclass_transform の扱い

dataclass_transform はヒントとして扱うが、初期実装では完全な runtime 同等性を仮定しない。
必要に応じて plugin/extractor に委譲する。


---

8.4 デフォルト値の解決元

Parameter の初期値は複数ソースから解決する。

8.4.1 優先順位

将来拡張を含む定義として、以下の優先順位を持つ。

1. runtime facts


2. CLI explicit override


3. parameter file


4. static callsite inference


5. function signature default


6. pyproject.toml


7. environment variables



初期実装では runtime facts を未実装とし、実際の優先順位は以下とする。

1. CLI explicit override


2. parameter file


3. static callsite inference


4. function signature default


5. pyproject.toml


6. environment variables



8.4.2 Provenance 保持

各 parameter は最終値だけでなく、値の供給元を保持する。

例:

{
  "seed": {
    "value": 42,
    "source": "cli"
  }
}


---

9. Parameter File 仕様

9.1 目的

Parameter File は、Notebook 生成時に使用する初期ハイパーパラメータを保存する JSON ファイルである。
一時利用にも永続利用にも使える。

9.2 用途

CLI 実行時の引数供給

Git 管理

Papermill 再実験

実験定義の永続化

Notebook デフォルト値の外部化


9.3 形式

JSON とする。

例:

{
  "config": {
    "lr": 0.01,
    "epochs": 10,
    "seed": 42
  }
}

または複数引数の場合:

{
  "train_path": "data/train.csv",
  "valid_path": "data/valid.csv",
  "seed": 42
}

9.4 補助マニフェスト

astronote は必要に応じて、解決済み parameter と provenance を保持する resolved manifest を別途出力できる。


---

10. 静的解析仕様

10.1 解析対象

Python module

Python script

src/ レイアウトを持つローカルプロジェクト


10.2 解析内容

AST parse

decorator 解決

entrypoint 発見

関数 signature 取得

型ヒント取得

import graph 構築

local module 展開

callsite 推定

parameter schema 生成


10.3 callsite 推定

静的解析により entrypoint 呼び出し箇所を探索し、引数初期値候補を推定する。

10.3.1 高信頼で扱うもの

literal

dict/list/tuple literal

dataclass constructor with literal fields

module-level simple constant


10.3.2 条件付きで扱うもの

Enum member

Path("...") 形式

単純な名前参照


10.3.3 初期実装で扱いを制限するもの

動的関数呼び出し結果

複雑な式

closure や lambda 依存

import 元の runtime 値

comprehension を含む複雑構造


callsite 推定値はあくまで候補であり、parameter file や CLI override より弱い。


---

11. import 展開仕様

11.1 方針

ローカルプロジェクトのモジュールを Notebook に展開可能とする。
ただし、無制限な flatten は行わない。

11.2 展開対象

初期実装では以下を原則とする。

project local module: 展開候補

standard library: 展開しない

third-party package: 展開しない


11.3 対象モジュール判定

以下のいずれかで判定する。

1. CLI / pyproject.toml による明示指定


2. src/ レイアウトの自動検出


3. module root の明示設定



11.4 非対応または制限対象

from x import *

dynamic import

複雑な re-export 連鎖

循環依存を前提とした強引な flatten


11.5 展開粒度

初期実装では module 単位または symbol 単位のいずれかを選択可能とするが、原則として 必要な symbol に限定した展開 を志向する。


---

12. Notebook 構成仕様

12.1 生成方式

Notebook は nbformat により構築する。

12.2 セル種別

初期実装では以下のコードセルを生成対象とする。

1. runtime/setup cell


2. parameter cell


3. import / dependency cell


4. entry definition cell


5. execution cell



必要に応じて markdown cell を将来追加可能とするが、初期実装では必須としない。

12.3 Parameter Cell

Papermill 互換のため、parameter cell には parameters タグを付与する。

12.4 Execution Cell

最終セルでは entrypoint を呼び出す。
Parameter Cell で定義された値を使用する。


---

13. セルメタデータ仕様

13.1 目的

生成セルとソースモジュールの対応付け、および差分更新のために metadata を保持する。

13.2 metadata namespace

astronote 固有 metadata は astronote 名前空間配下に記録する。

例:

{
  "astronote": {
    "cell_id": "mod:myproj.train|fn:run|kind:entry-def",
    "source_module": "myproj.train",
    "source_qualname": "run",
    "kind": "entry-def",
    "source_hash": "sha256:..."
  }
}

13.3 stable cell id

差分更新の安定性のため、line number ではなく以下を基本とする。

source module

qualname

semantic kind


これにより、コード位置の変動に強い識別子を生成する。


---

14. 差分更新仕様

14.1 目的

既存 Notebook に対して、生成対象セルのみを再生成し、必要なセルのみ更新する。

14.2 更新対象

Generated Cell のみ

metadata により source と対応付け可能なセル


14.3 保持対象

明示的に preserve とされたセル

ユーザー編集セル


14.4 更新方式

1. 既存 Notebook を読み込む


2. astronote metadata を持つセルを特定する


3. 新しい Static IR / Resolved IR を生成する


4. cell_id 単位で再生成・置換する


5. preserve 対象セルは維持する




---

15. pyproject.toml 仕様

15.1 目的

astronote のツール設定をプロジェクト単位で管理する。

15.2 管理対象

entry decorator 名

module roots

include / exclude modules

env prefix

default parameter file path

parameter precedence policy

update policy


15.3 例

[tool.astronote]
entry_decorator = "astronote.notebook_entry"
module_roots = ["src"]
include_modules = ["myproj"]
exclude_modules = ["myproj.tests"]
default_params_file = "experiments/default.params.json"
env_prefix = "ASTRONOTE_"
parameter_precedence = [
  "runtime",
  "cli",
  "file",
  "callsite",
  "signature",
  "pyproject",
  "env"
]
update_mode = "preserve_user_cells"

15.4 役割の制約

pyproject.toml は主にツール設定を持つ。
実験値そのものの主保存先は Parameter File とする。


---

16. 環境変数仕様

16.1 目的

環境依存のデフォルト値や振る舞い切り替えを行う。

16.2 用途例

Notebook 実行環境フラグ

default params file path override

debug mode

update policy override


16.3 優先順位

環境変数は parameter source としては最下位に近い位置づけとする。


---

17. CLI 仕様

17.1 基本コマンド

inspect

静的解析結果を表示する。

astronote inspect src/myproj/train.py

表示対象例:

検出 entrypoint

関数 signature

parameter schema

callsite 推定結果

import 展開候補


params

parameter schema または parameter file 雛形を出力する。

astronote params src/myproj/train.py

build

Notebook を生成する。

astronote build src/myproj/train.py -o dist/train.ipynb
astronote build src/myproj/train.py --params experiments/exp001.json -o dist/train.ipynb
astronote build src/myproj/train.py --params experiments/exp001.json --set seed=42 -o dist/train.ipynb

update

既存 Notebook を差分更新する。

astronote update dist/train.ipynb


---

17.2 CLI parameter 指定

--params

Parameter File を指定する。

--set

単一 parameter override を指定する。

例:

astronote build train.py --set seed=42 --set lr=0.01

--entrypoint

複数 entrypoint がある場合に対象を明示する。


---

18. 中間表現仕様

18.1 Static IR

AST 解析結果を表す。

保持項目例:

source path

module name

entrypoint

function signature

type info

callsite candidates

import expansion plan

cell plan skeleton


18.2 Resolved IR

Static IR に parameter 解決結果をマージしたもの。

保持項目例:

resolved parameters

parameter provenance

final notebook cell plan

metadata

build info


18.3 将来拡張

runtime facts は将来的に Resolved IR へマージ可能な source として扱う。


---

19. エラーハンドリング方針

19.1 エラーとするケース

entrypoint が存在しない

entrypoint が複数あり未指定

解析不能な decorator 解決

import 展開対象が循環し、解決不能

parameter JSON が schema と整合しない

既存 Notebook に必要 metadata が無いのに update を要求した


19.2 警告とするケース

callsite 推定が不完全

一部 import を展開できない

unsupported type を含む

dynamic import を無視した

Parameter File に未使用キーがある



---

20. 非機能要件

20.1 再現性

同一 source、同一 params、同一設定からは同一構造の Notebook が生成されること。

20.2 安定性

コメントやセル境界コメント等に依存せず、AST ベースで安定した変換を行うこと。

20.3 保守性

Static IR / Resolved IR / Notebook emitter を分離し、将来 runtime source を追加可能であること。

20.4 速度

CLI の inspect や params は、コード実行を伴わず高速に動作すること。

20.5 拡張性

extractor plugin、runtime facts、追加 parameter source を将来的に導入可能であること。


---

21. 初期実装スコープ

含む

AST ベース解析

@notebook_entry 検出

関数 signature 解析

dataclass ベース parameter 推定

Parameter File 読み込み

CLI override

callsite 推定

local module の限定展開

nbformat による Notebook 生成

metadata による差分更新

pyproject.toml 設定読み込み


含まない

実行時キャプチャ

動的 decorator 解決

third-party package 展開

完全な Python 意味解析

Notebook を正本とする編集フロー



---

22. 将来拡張

runtime facts source の追加

extractor plugin の充実

pydantic / attrs 対応強化

Markdown セルの自動生成

richer dependency graph

notebook lint / validation

Kaggle 向け専用最適化モード

bundle 戦略との連携



---

付録A. 最小使用例

from dataclasses import dataclass
from astronote import notebook_entry

@dataclass
class TrainConfig:
    lr: float = 0.01
    epochs: int = 10
    seed: int = 42

@notebook_entry
def run(config: TrainConfig) -> None:
    print(config)

astronote build train.py -o dist/train.ipynb
astronote build train.py --params experiments/exp001.json -o dist/train.ipynb


---

付録B. 設計原則の要約

正本は script

Notebook は派生成果物

解析は AST ベース

初期実装は静的解析のみ

parameter は JSON で外出し可能

parameter source の優先順位は明示

provenance を保持

metadata により差分更新可能

Notebook は Read Only 的に扱う

