# ADK Bidi-Streaming: リアルタイムマルチモーダルAIエージェント開発のチートシート

リアルタイム音声AIエージェントの構築は簡単ではありません。スケーラブルな非同期イベント処理のフレームワーク構築、遅延のないオーディオと画像のストリーミング、会話の自然な割り込みの扱い、再接続をまたいで保持されるセッション状態などなど、解決すべきことはたくさんあります。それらすべてをゼロから実装しようとすると、数週間で終わるはずのプロジェクトがインフラ構築だけに数ヶ月を要してしまうこともあります。

もし、そうした面倒な作業をスキップして、本当に重要なこと—エージェントの動作とユーザー体験—に集中できるとしたらどうでしょう？

それこそが、Googleの[Agent Development Kit（ADK）](https://google.github.io/adk-docs/)が実現することです。新しく公開された[ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/)では、リアルタイム音声AIエージェントのアーキテクチャの基礎から本番デプロイまでを網羅する全5部構成の包括的な開発者ガイドを提供しています：

| パート | フォーカス | 学べること |
|--------|-----------|-----------|
| [Part 1](https://google.github.io/adk-docs/streaming/dev-guide/part1/) | 基礎 | アーキテクチャ、Live APIプラットフォーム、アプリケーション構成 |
| [Part 2](https://google.github.io/adk-docs/streaming/dev-guide/part2/) | アップストリーム | LiveRequestQueueによるテキスト、オーディオ、ビデオの送信 |
| [Part 3](https://google.github.io/adk-docs/streaming/dev-guide/part3/) | ダウンストリーム | イベント処理、ツール実行、マルチエージェントワークフロー |
| [Part 4](https://google.github.io/adk-docs/streaming/dev-guide/part4/) | 設定 | セッション管理、クォータ、本番環境の制御 |
| [Part 5](https://google.github.io/adk-docs/streaming/dev-guide/part5/) | マルチモーダル | オーディオ仕様、モデルアーキテクチャ、高度な機能 |

ガイドには完全な動作デモも含まれています—ローカルで実行して試すことができる、Web UIを備えたFastAPI WebSocketサーバーです：

![ADK Bidi-streaming Demo](assets/bidi-demo-screen.png)

**[bidi-demoを試す →](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo)**

この記事では、ガイドをインフォグラフィックスにまとめたチートシートに凝縮してみました。

---

## アーキテクチャを理解する

各機能の詳細に入る前に、それぞれのコンポーネントがどのように組み合わされるのかを概観しましょう。ADK Bidi-streamingは、それぞれ異なる責務を持つ3つのレイヤーで、クリーンな[関心の分離](https://google.github.io/adk-docs/streaming/dev-guide/part1/#14-adk-bidi-streaming-architecture-overview)を実現しています。

![ADK Bidi-streaming High-Level Architecture](assets/Bidi_arch.jpeg)

**アプリケーション層はあなたが開発します。** これには、ユーザーが操作するクライアントアプリケーション（Webやモバイルアプリ等）と、接続を管理するトランスポートサーバーが含まれます。ここでは[FastAPI](https://fastapi.tiangolo.com/)がポピュラーな選択肢ですが、リアルタイム通信をサポートするどんなフレームワークでも利用できます。また、AIエージェントを定義する[Agent](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-agent)も開発者が実装します。

**ADKがオーケストレーションを処理します。** ADKは、面倒なインフラの責務を肩代わりする3つの主要コンポーネントを提供します。[LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/)は受信メッセージのキューイングを一括管理します。[Runner](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-runner)はセッションのライフサイクルと会話状態を管理します。そして内部のLLMFlowは、モデルとの面倒なやりとりを管理します。

**GoogleがリアルタイムAIモデルを提供します。** Googleは、オーディオ、ビデオ、[自然な割り込み](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag)をサポートしたリアルタイム低遅延AI処理を実現する[Live API](https://google.github.io/adk-docs/streaming/dev-guide/part1/#12-gemini-live-api-and-vertex-ai-live-api)を提供します。Live APIには次の2種類があります：迅速なプロトタイピングに適した[Gemini Live API](https://ai.google.dev/gemini-api/docs/live)、およびエンタープライズ利用に適した[Vertex AI Live API](https://cloud.google.com/vertex-ai/generative-ai/docs/live-api)です。
> **ポイント：** 図中の双方向矢印は、同時並行通信を表しています。ユーザーは人間の会話と同様に、AIの発言中に割り込むことができます。これはリクエスト-レスポンスAPIとは根本的に異なり、ADK Bidi-streamingによる音声AIがロボット的ではなくより自然に感じられる理由です。

---

## なぜ生のLive APIではなくADKなのか？

各パーツがどこに収まるかを理解したところで、自然な疑問が浮かびます：なぜLive API上で直接アプリを構築するのではなくADKを使用するのでしょうか？　2つのアプローチを並べて比較すると、答えは明白になります。

![Raw Live API vs. ADK Bidi-streaming](assets/live_vs_adk.png)

生のLive APIでは、これらすべての機能をあなたが実装しなくてはなりません。例えば、ツール実行では関数呼び出しを検出し、コードを呼び出し、レスポンスをフォーマットし、送り返す必要があります。また進行中のオーディオストリームの切断に備えて、再接続ロジックを実装し、セッションハンドルをキャッシュし、状態を復元します。セッション永続化のために、スキーマを設計し、セッションデータのシリアル化を処理し、ストレージ層を管理する必要があります。

**ADKはこれらすべてを宣言的設定で置き換えます。** ツールは自動的に並列実行されます。またLive APIとの接続タイムアウトが発生すると、その接続は透過的に再接続されます。セッション内容は指定したデータベースに自動的に永続化されます。エージェントが送信するイベントは型付きのPydanticモデルとして生成され、取り扱いも容易です。

ADK Bidi-streamingのドキュメントでは、これらについて詳細な[機能の比較](https://google.github.io/adk-docs/streaming/dev-guide/part1/#13-adk-bidi-streaming-for-building-realtime-agent-applications)が記載されています：

| 機能 | 生のLive API | ADK Bidi-streaming |
|------|--------------|-------------------|
| エージェントフレームワーク | ゼロから構築 | ツール、評価、セキュリティ付きのシングル/マルチエージェント |
| [ツール実行](https://google.github.io/adk-docs/streaming/dev-guide/part3/#automatic-tool-execution-in-run_live) | 手動処理 | 自動並列実行 |
| [接続管理](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-session-resumption) | 手動再接続 | 透過的セッション再開 |
| [イベントモデル](https://google.github.io/adk-docs/streaming/dev-guide/part3/#the-event-class) | カスタム構造 | 統一された型付きEventオブジェクト |
| 非同期フレームワーク | 手動調整 | LiveRequestQueue + run_live()ジェネレーター |
| [セッション永続化](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-sessionservice) | 手動実装 | SQL、Vertex AI、またはインメモリの組み込み |

> **ポイント：** ADKは数ヶ月のインフラ開発を数日のアプリケーション開発に短縮します。ストリーミングの仕組みではなく、エージェントが何をするかに集中できます。

---

## アプリケーションの構成

ADK Bidi-streamingアプリケーションは、[4段階のフェーズ](https://google.github.io/adk-docs/streaming/dev-guide/part1/#15-adk-bidi-streaming-application-lifecycle)に従って構成されます。

![ADK Bidi-streaming Application Lifecycle](assets/app_lifecycle.png)

### フェーズ1：アプリケーション初期化

サーバー起動時に、アプリケーションの実行中に利用される3つの基礎的なコンポーネントを作成します。まず、AIエージェントのモデル、ツール、そして振る舞いを定義した持つ[Agentを作成](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-agent)します。次に、ユーザーセッションごとに[SessionServiceを作成](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-sessionservice)します。つづいて、セッションの双方向通信を管理する[Runnerを初期化](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-runner)します。

これらのコンポーネントはステートレスで、Pythonの非同期コンテキストで動作するため、単一のRunnerで数千の同時ユーザーを処理できます。

### フェーズ2：セッション初期化

ユーザーセッションの開始時に、ストリーミングセッションをセットアップします。過去の会話履歴を復元するために[Sessionを取得または作成](https://google.github.io/adk-docs/streaming/dev-guide/part1/#get-or-create-session)します。またモダリティ（オーディオまたはテキスト）、文字起こし設定等の各種機能を指定するために[RunConfigを設定](https://google.github.io/adk-docs/streaming/dev-guide/part1/#create-runconfig)します。メッセージバッファリング用に[新しいLiveRequestQueueを作成](https://google.github.io/adk-docs/streaming/dev-guide/part1/#create-liverequestqueue)します。そして[run_live()イベントループを開始](https://google.github.io/adk-docs/streaming/dev-guide/part3/#how-run_live-works)します。

### フェーズ3：双方向ストリーミング

このイベントループ内では。2つの同時非同期タスクが同時に実行されます：アップストリームタスクはクライアントからのメッセージをキューを通じてエージェントに[メッセージを送信](https://google.github.io/adk-docs/streaming/dev-guide/part1/#send-messages-to-the-agent)し、ダウンストリームタスクはエージェントから[イベントを受信](https://google.github.io/adk-docs/streaming/dev-guide/part1/#receive-and-process-events)してクライアントに転送します。

ユーザーはAIの応答中に割り込んで話すことができます。AIは発言の途中での[割り込み](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag)を検出できます。これは双方向通信の大きなメリットであり、交互にしか話せない単方向通信との違いです。

### フェーズ4：セッション終了

接続が終了するとき—ユーザーが切断したか、タイムアウトが発生したか、エラーが発生したかに関わらず—[LiveRequestQueueを閉じ](https://google.github.io/adk-docs/streaming/dev-guide/part2/#control-signals)ます。これにより終了シグナルが送信され、run_live()ループが停止し、セッション状態が将来の再開のために永続化されます。

> **ポイント：** フェーズ4からフェーズ2への矢印はセッションの継続性を表しています。ユーザーが再接続するとき—たとえ数日後でも—会話履歴はSessionServiceから復元されます。Live APIが管理するセッション情報は一時的にしか保持されませんが、ADKセッションは永続的に保存されます（インメモリではなく、SQLやVertex AIなどの永続的なセッションストアを指定した場合）。

---

## アップストリームフロー：LiveRequestQueue

クライアントからAIエージェントへのメッセージは、すべて[LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/#liverequestqueue-and-liverequest)を介して送信されます。テキスト、オーディオ、制御シグナルのそれぞれに適したAPIを提供しますが、すべてを統合する1つのキューを内部に備えます。

![ADK Bidi-Streaming: Upstream Flow with LiveRequestQueue](assets/live_req_queue.png)

**テキストの送信**は簡単です。ユーザーからのメッセージを受け取ったら、Contentオブジェクトでラップして[`send_content()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#send_content-sends-text-with-turn-by-turn)を呼び出します。これにより即座にレスポンス生成がトリガーされます。

**オーディオのストリーミング**は異なる動作をします。ユーザーが話している間、小さなチャンク（50-100msを推奨）で連続的に[`send_realtime()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#send_realtime-sends-audio-image-and-video-in-real-time)を呼び出します。モデルはオーディオをリアルタイムで処理し、Voice Activity Detection（音声発話検知）機能を使用してユーザーが話し終わったかを判断します。

**手動ターン制御**は必要に応じて利用できます。クライアント側でPush-to-talk（PTT）ボタン（送信ボタン）のインタフェースを利用している場合や、クライアント側VADを使用している場合、[`send_activity_start()`と`send_activity_end()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#activity-signals)で明示的に発話境界を通知します。

**セッション終了**は[`close()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#control-signals)を通じて行われます。これにより、タイムアウトまかせでセッションをぶつ切れにするのではなく、Live APIにスムーズにセッション終了するよう伝えます。

キューはPythonのasyncio.Queue上に構築されており、[イベントループ内でノンブロッキングかつスレッドセーフ](https://google.github.io/adk-docs/streaming/dev-guide/part2/#concurrency-and-thread-safety)です。メッセージは[FIFO順](https://google.github.io/adk-docs/streaming/dev-guide/part2/#message-ordering-guarantees)で処理されます—最初に送信したものが最初に到着します。

---

## ダウンストリームフロー：run_live()メソッド

AIエージェントからユーザーへのメッセージは、[`run_live()`](https://google.github.io/adk-docs/streaming/dev-guide/part3/)を介して処理されます。この非同期ジェネレーターはADK Bidi-streamingの心臓部であり、バッファを介さずリアルタイムにイベントを生成します。

![Comprehensive Summary of ADK Live Event Handling: The run_live() Method](assets/run_live.png)

### run_live()の動作方法

このメソッドは3つのパラメータを受け取ります：**会話の識別ID**（user_idとsession_id）、**送信キュー**（LiveRequestQueue）、**セッション設定**（RunConfig）。戻り値として、[Eventオブジェクト](https://google.github.io/adk-docs/streaming/dev-guide/part3/#the-event-class)を生成する非同期ジェネレーターを返します。

```python
async for event in runner.run_live(
    user_id=user_id,
    session_id=session_id,
    live_request_queue=queue,
    run_config=config
):
    # 到着した各イベントを処理
    await websocket.send_text(event.model_dump_json())
```

### 7つのイベントタイプ

7つのイベントタイプの役割を理解することで、ADK Bidi-streamingの能力を活かした洗練されたリアルタイムUIを実現できます。

[テキストイベント](https://google.github.io/adk-docs/streaming/dev-guide/part3/#text-events)には、`event.content.parts[0].text`にモデルからのテキストレスポンスが含まれます。生成途中からインクリメンタルに部分的なレスポンス（`partial=True`）が到着し、その後にすべてをまとめたレスポンス（`partial=False`）が到着します。

[オーディオイベント](https://google.github.io/adk-docs/streaming/dev-guide/part3/#audio-events)には2つの形式があります。リアルタイム再生用にはインラインオーディオ（`inline_data`）がストリーミングで到着します。一方、オーディオの永続化設定を有効にすると、ファイル保存されたオーディオ（`file_data`）を受け取ることができます。

[文字起こしイベント](https://google.github.io/adk-docs/streaming/dev-guide/part3/#transcription-events)は、ユーザー入力とモデル出力の両方に対して音声からテキストへの文字起こしを利用できます。アクセシビリティ、ログ記録、音声インタラクションのデバッグに非常に有用です。

[メタデータイベント](https://google.github.io/adk-docs/streaming/dev-guide/part3/#metadata-events)はトークン使用量を報告します—コスト監視とクォータ管理に不可欠です。

[ツール呼び出しとレスポンスイベント](https://google.github.io/adk-docs/streaming/dev-guide/part3/#tool-call-events)はツール実行をモニタできます。ツールの呼び出しはADKによって自動的に実行されます。

[エラーイベント](https://google.github.io/adk-docs/streaming/dev-guide/part3/#error-events)は`error_code`と`error_message`フィールドでエラーの発生を通知します。回復可能なエラー（レート制限等）もあれば、終端的なエラー（安全性違反等）もあります。

### フロー制御フラグ

会話の流れを制御する3つのフラグが利用できます。

[**`partial`**](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-partial)は、インクリメンタルな部分レスポンスか、フルのレスポンスかを表します。例えばUI側ではエージェントメッセージに表示するタイピング中アイコン「…」の表示の制御に使えます。

[**`interrupted`**](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag)は、モデルがまだ応答中にユーザーが話し始めたことを通知します。例えばUI側ではエージェント音声の再生をすぐに停止するために使います。

[**`turn_complete`**](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-turn_complete-flag)は、モデルがレスポンス全体を完了したことを示します。例えばUI側ではタイピング中アイコンを消すタイミングとして使えます。

> **ポイント：** これらのフラグは音声AIエージェントとの会話を自然に感じさせるために利用できます。これらがなければ、ユーザーはAIエージェントが話し終わるのをじっと待ってから応答する必要があります。

---

## 実際の例：音声検索アプリの流れ

これらのコンポーネントがどのように連携するかを見るため、サンプルアプリ[bidi-demo](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo)を例にとって一通りの流れを追ってみましょう。まず、ユーザーがAIエージェントに尋ねます：*「東京の天気は？」*

**1. オーディオキャプチャ → キュー**
ブラウザは16kHzでマイク入力をキャプチャし、音声データのチャンクに変換して、WebSocketのバイナリフレーム経由で送信します。サーバーは音声データを受信し、`live_request_queue.send_realtime(audio_blob)`を呼び出します。

**2. VAD検出**
Live APIのVoice Activity Detection（音声発話検知）機能がユーザーが話すのをやめたことを検知します。蓄積されたオーディオの処理がトリガーされます。

**3. 文字起こしイベント**
`input_transcription.text = "東京の天気は？"`という内容の文字起こしイベントを受信します。チャットUIにこれを表示して、ユーザーが自分の言葉が認識されたことを確認できるようにします。

**4. ツール実行**
モデルは東京の天気を調べるために`google_search`ツールを呼び出すことを決定します。ADKがGoogle検索ツールを自動的に実行し、天気データを含むツールレスポンスイベントを受信します。

**5. オーディオレスポンス**
モデルは音声レスポンスを生成します。`inline_data`を持つオーディオレスポンスイベントが到着します。クライアントはリアルタイム再生のためにこれらをAudioWorkletに渡し、音声が再生されます：*「東京の現在の天気は22度で晴れです。」*

**6. ターン完了**
最後に、`turn_complete=True`のイベントが到着します。UIは「...」インジケーターを削除して、エージェントが話し終わったことを示すことができます。

このフロー全体は2秒未満で完了します。ユーザーは表面下で起こっているLiveRequestQueue、Eventタイプ、セッション管理を意識せず、自然な会話として体験します。

---

## RunConfigによるセッション設定

[RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part4/)はストリーミングセッションのコントロールセンターです。セッションのあらゆる側面—オーディオフォーマットからコスト制限まで—がここで設定されます。

![Comprehensive Summary of Live API RunConfig](assets/runconfig.png)

### 必須パラメータ

[**`response_modalities`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#response-modalities)は、モデルがテキストまたはオーディオで応答するかを決定します。セッションごとに1つを選択する必要があります—テキストチャットアプリケーションには`["TEXT"]`、音声には`["AUDIO"]`。ネイティブオーディオモデルはオーディオ出力を必要とし、ハーフカスケードモデルは両方をサポートします。

[**`streaming_mode`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#streamingmode-bidi-or-sse)はADKがLive APIとの接続に使用するトランスポートプロトコルを指定します。BIDIはLive APIへのWebSocketを使用し、完全な双方向ストリーミング、割り込み、VADを提供します。SSEは標準Gemini APIへのHTTPストリーミングを使用します—よりシンプルですがテキストのみのサポートになります。

[**`session_resumption`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-session-resumption)はLive APIへの自動再接続を有効にします。Live APIとのWebSocket接続は通常10分程度でタイムアウトします。セッション再開を有効にすると、ADKは透過的に再接続を処理します—アプリケーション側ではこの中断を意識する必要がありません。

[**`context_window_compression`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-context-window-compression)は古い会話履歴を要約してコンテキストウィンドウを圧縮する機能です。セッションの時間制限（通常オーディオは15分、ビデオは2分）とトークン数の制限という2つの課題に対処できます。長時間実行する可能性のあるセッションで利用します。

### 本番環境の制御

[**`max_llm_calls`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#max_llm_calls)はセッションごとの呼び出しを制限します—コスト制御に有用ですが、SSEモードにのみ適用されます。BIDIストリーミングでは、ターンカウントをアプリケーション側で実装します。

[**`save_live_blob`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#save_live_blob)はオーディオとビデオをアーティファクトストレージに保存します。デバッグや監査機能などに便利です。ただし、ストレージコストが発生するので注意してください。

[**`custom_metadata`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#custom_metadata)は任意のキー-値データをすべてのイベントに添付します。ユーザーセグメンテーション、A/Bテスト、またはデバッグコンテキストに使用します。

### [セッションタイプの理解](https://google.github.io/adk-docs/streaming/dev-guide/part4/#understanding-live-api-connections-and-sessions)

ADK Bidi-streamingを理解するうえでわかりにくい概念が、ADKセッションとLive APIセッションの違いです。

[**ADKセッション**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#adk-session-vs-live-api-session)は永続的です。SessionService（データベース、Vertex AI、またはメモリ）に存在し、メモリ保存時をのぞいてサーバーが再起動しても失われません。ユーザーが数日後に戻ってきても、会話履歴は保持されています。

[**Live APIセッション**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-connections-and-sessions)は一時的に維持されるセッションです。アクティブな`run_live()`呼び出し中にのみ存在します。ループが終了すると、Live APIセッションは破棄されますが、ADKはセッション情報をADKセッションに自動的に永続化してくれます。

> **クォータの計画：** Gemini Live APIはティアに応じて50-1,000の同時セッションを許可します。Vertex AIはプロジェクトごとに最大1,000をサポートします。これらの制限を超える可能性のあるアプリケーションでは、[ユーザーキュー付きセッションプーリング](https://google.github.io/adk-docs/streaming/dev-guide/part4/#architectural-patterns-for-managing-quotas)を実装する必要があります。

---

## マルチモーダル機能

ADK Bidi-streamingはオーディオ、画像、ビデオをサポートする完全な[マルチモーダルプラットフォーム](https://google.github.io/adk-docs/streaming/dev-guide/part5/)です。

![Comprehensive Summary of ADK Live API Multimodal Capabilities](assets/multimodal.png)

### オーディオ機能

[**入力オーディオ**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#sending-audio-input)は16ビットPCM、モノラル、16kHzである必要があります。例えばブラウザのAudioWorkletでマイク入力をキャプチャし、Float32サンプルをInt16に変換して、WebSocket経由でストリーミングします。

[**出力オーディオ**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#receiving-audio-output)は16ビットPCM、モノラル、24kHzで到着します。ネットワークジッターを吸収してスムーズな再生を確保するため、AudioWorkletプレーヤーでバッファを実装して再生します。

### 画像とビデオ：フレームごと

画像とビデオの両方が同じメカニズムを使用します—[`send_realtime()`経由で送信されるJPEGフレーム](https://google.github.io/adk-docs/streaming/dev-guide/part5/#how-to-use-image-and-video)。推奨解像度は768×768で、最大フレームレートは1 FPSです。

このアプローチは視覚的コンテキストの共有（製品を見せる、部屋の様子を見せる等）にはよく機能しますが、リアルタイムな動作の認識には適していません。1 FPSの制限のため、すばやい動きを捉えることはできません。

### モデルアーキテクチャ

Live APIでは、アーキテクチャの異なる2つのタイプのモデルが提供されています：

[**ネイティブオーディオモデル**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#native-audio-models)はテキスト中間物なしでオーディオをエンドツーエンドで処理します。より自然なトーンを再現し、[Affective Dialog](https://google.github.io/adk-docs/streaming/dev-guide/part5/#proactivity-and-affective-dialog)（感情適応）や[Proactivity](https://google.github.io/adk-docs/streaming/dev-guide/part5/#proactivity-and-affective-dialog)（自発的な提案）などの高度な機能が利用できます。現在利用可能なモデル名は`gemini-2.5-flash-native-audio-preview`です。

[**ハーフカスケードモデル**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#half-cascade-models)はオーディオをテキストに変換し、処理してから音声を合成します。TEXTとAUDIOの両方のレスポンスモダリティをサポートし、より高速なテキストレスポンスとより予測可能なツール実行を提供します。

### 高度な機能

[**オーディオ文字起こし**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#audio-transcription)はデフォルトで有効です。ユーザーの発話とモデルの発話の両方が文字起こしされ、別々のイベントフィールドとして到着します。アクセシビリティの実装と会話ログに不可欠です。

[**Voice Activity Detection（音声発話検知）**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-activity-detection-vad)は、ユーザーが話し始めたり話し終わったりするタイミングを自動的に検出します。クライアント側はオーディオを継続的にストリーミングするだけで、モデル側にターン交代のタイミング管理を任せます。

[**音声種別設定**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-configuration-speech-config)では利用可能な音声種別から選択できます。複数のエージェントがそれぞれに異なる音声を持つようなマルチエージェント構成ではエージェントごとに音声種別を設定できます。

> **ポイント：** Affective DialogやProactivityのような高度な対話能力を備えた自然な会話には、ネイティブオーディオモデルを使用します。一方、ツール実行の信頼性を優先するアプリケーションや、すばやいテキストレスポンスが必要なケースでは、ハーフカスケードを使用します。

---

## すべてをまとめる

多くの内容をカバーしました。各パーツがどのように一貫したシステムに接続するかを見てみましょう：

**[アーキテクチャ](https://google.github.io/adk-docs/streaming/dev-guide/part1/#14-adk-bidi-streaming-architecture-overview)**：ADK Bidi-streamingでは個々の機能がクリーンに分離されています。アプリケーションとエージェント定義は開発者が用意し、ADKがオーケストレーションを処理し、GoogleがLive APIモデルを提供します。

**[ADK vs 生のAPI](https://google.github.io/adk-docs/streaming/dev-guide/part1/#13-adk-bidi-streaming-for-building-realtime-agent-applications)**：ADKは自動ツール実行、透過的再接続、型付きイベント、組み込み永続化を通じて、数ヶ月かかるようなインフラ開発作業を不要とします。

**[アプリケーション構成](https://google.github.io/adk-docs/streaming/dev-guide/part1/#15-adk-bidi-streaming-application-lifecycle)**：起動時に1回初期化し、セッションごとに設定し、双方向にストリーミングし、クリーンに終了します。

**[LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/)**：アップストリーム通信をまかないます。4つのメソッドがすべての入力タイプを処理します：テキスト、オーディオ、アクティビティシグナル、終了。

**[run_live()](https://google.github.io/adk-docs/streaming/dev-guide/part3/)**：ダウンストリームイベントをストリーミングします。7つのイベントタイプがテキスト、オーディオ、文字起こし、メタデータ、ツール、エラーをカバーします。3つのフラグが会話フローを制御します。

**[RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part4/)**：セッションのふるまいを宣言的に設定します。モダリティ、再開、圧縮、制御などを指定できます。

**[マルチモーダル機能](https://google.github.io/adk-docs/streaming/dev-guide/part5/)**：テキストに加えてオーディオ、画像、そして動画をサポートします。特定のサンプルレートでのオーディオ、JPEGフレームとしての画像とビデオ、VADや文字起こしなどの高度な機能を提供します。

---

## 始めるには

ADK Bidi-streamingを始めてみる準備はできましたか？　以下にスタートポイントを示します。

**まずデモを試してください。** [bidi-demo](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo)は、ローカルで実行できるFastAPI実装です。WebSocketハンドラー、同時タスク、オーディオ処理、UIなど、この記事で紹介した主要なポイントを試せます。

**開発者ガイドを読んでください。** [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/)は、実装の詳細、コードサンプル、エッジケースについて詳細な解説を提供します。

**より広いADKエコシステムを探索してください。** [公式ADKドキュメント](https://google.github.io/adk-docs/)は、エージェント設計、ツール開発、セッション管理、デプロイパターンをカバーしています。
